# OpenAI Tool Registry Design

## Purpose

MendCode currently has a provider-driven Agent loop and an OpenAI-compatible JSON provider path. The next step is to let real OpenAI-protocol models use structured tool calls directly, while keeping MendCode's internal execution, permission, and observation model coherent.

This design introduces a Hybrid ToolRegistry. The main path is OpenAI native `tool_calls`, generated from the registry. The current JSON Action protocol can remain as a fallback and deterministic test path, but it is not the primary user-facing model interface for this slice.

## Product Fit

This advances the current TUI Agent route by making the model's tool use explicit and structured:

```text
ToolRegistry -> OpenAI tools schema -> model tool_calls -> ToolInvocation
  -> Permission Gate -> Tool Execution -> Observation -> tool result message
```

The Agent loop should still operate on MendCode-owned abstractions. OpenAI message shapes stay inside the provider adapter and context builder.

## Scope

In scope:

- Add a central `ToolRegistry` for structured tools.
- Represent each tool with a `ToolSpec` containing its name, description, args model, executor, risk level, permission policy, and observation formatter.
- Add strong Pydantic args models for supported tools.
- Generate OpenAI-compatible `tools` JSON Schema from the registry.
- Parse OpenAI native `tool_calls` into internal `ToolInvocation` objects.
- Convert tool execution results back into OpenAI `role="tool"` messages with the matching `tool_call_id`.
- Keep existing JSON Action parsing available as a fallback or test channel.
- Preserve existing permission and shell safety behavior.
- Keep tool output truncated and structured before it is sent back to the model.

Out of scope:

- Anthropic or non-OpenAI provider compatibility.
- Parallel execution of multiple tool calls.
- Long-running or interactive shell sessions.
- Automatic commit, push, install, or network operations.
- A general terminal passthrough as the primary tool interface.
- A new memory or vector-retrieval layer for tool output.

## Architecture

The registry is the single source of truth for tools. Each tool should be registered as a small, typed specification:

```python
ToolSpec(
    name="read_file",
    description="Read a UTF-8 text file inside the current repo.",
    args_model=ReadFileArgs,
    executor=read_file_executor,
    risk_level=ToolRisk.READ_ONLY,
    permission_policy=read_only_policy,
    observation_formatter=format_read_file_observation,
)
```

Core fields:

- `name`: public tool name shown to the model and used for dispatch.
- `description`: concise model-facing description.
- `args_model`: Pydantic model used for JSON Schema generation and runtime validation.
- `executor`: implementation function that performs the tool work.
- `risk_level`: broad category used for safety decisions.
- `permission_policy`: tool-specific decision for auto-run, confirmation, or rejection.
- `observation_formatter`: result compressor for the next model step.

The provider adapter asks the registry for OpenAI tool definitions. The Agent loop should not manually build provider-specific schemas.

## Tool Invocation Model

Provider-specific tool calls should be normalized before execution:

```python
ToolInvocation(
    id="call_xxx",
    name="read_file",
    args={"path": "app/agent/loop.py"},
    source="openai_tool_call",
)
```

The same internal invocation type can also represent the JSON Action fallback:

```python
ToolInvocation(
    id=None,
    name="read_file",
    args={"path": "app/agent/loop.py"},
    source="json_action",
)
```

Execution code should only depend on `ToolInvocation`, `ToolSpec`, and `Observation`, not on raw OpenAI response objects.

## Provider Data Flow

The OpenAI-compatible provider should use native tool calling as the main route:

1. Build chat messages from the problem statement, verification commands, prior assistant messages, and prior observations.
2. Generate `tools` from `ToolRegistry`.
3. Send the request using the OpenAI-compatible API.
4. If the assistant response has `tool_calls`, normalize each call into `ToolInvocation`.
5. The Agent loop validates and executes each invocation sequentially.
6. Each result is converted into a `role="tool"` message with the original `tool_call_id`.
7. The next provider call includes the assistant tool-call message and matching tool result messages.
8. The loop continues until the model returns a final response or the loop stops for confirmation, failure, or budget exhaustion.

The first implementation should execute multiple tool calls sequentially in the order returned by the model. It should not parallelize them because tool calls can depend on shared workspace state and permission decisions.

## Agent Loop Responsibilities

`AgentLoop` remains provider-neutral. It is responsible for:

- loop state and step budget
- normalized action or tool invocation handling
- args validation through the registry
- permission decisions
- tool execution
- observation history
- verification gate behavior
- final result status

`AgentLoop` should not:

- generate OpenAI `tools` schema
- manipulate OpenAI message dictionaries directly
- know about `tool_call_id` transport details beyond receiving normalized invocation IDs

## Tool Set

The first registry should cover the tools already implied by the current Agent contract:

- `read_file`: read bounded text from a repo-local file.
- `list_dir`: list entries under a repo-local directory.
- `glob_file_search`: find files matching repo-local glob patterns.
- `rg`: run structured ripgrep searches with result limits.
- `git`: expose a safe structured subset of Git operations.
- `apply_patch`: validate and apply or propose repo-local patches according to permission policy.
- `run_shell_command`: restricted fallback for commands without a structured tool.
- `run_command`: verification-only command path, preserving its existing semantics.

Prefer structured tools over shell. `run_shell_command` is a fallback, not the main way for the model to inspect the repo.

## Permission Model

Tool risk levels should be explicit:

- `READ_ONLY`: auto-run by default.
- `WRITE_WORKTREE`: requires patch or tool confirmation unless the current workflow explicitly permits it.
- `SHELL_RESTRICTED`: delegates to the existing shell policy.
- `DANGEROUS`: blocked by default, or elevated to explicit user confirmation only for carefully whitelisted cases.

Suggested classifications:

- `READ_ONLY`: `read_file`, `list_dir`, `glob_file_search`, `rg`, `git status`, `git diff`, `git log`
- `WRITE_WORKTREE`: `apply_patch`
- `SHELL_RESTRICTED`: `run_shell_command`
- `DANGEROUS`: `git reset`, `git checkout`, `git clean`, `git commit`, `git push`, installs, network commands, destructive shell commands

The `git` tool should not be an arbitrary command passthrough. It should expose structured operations such as:

```json
{ "operation": "status" }
{ "operation": "diff", "path": "app/agent/loop.py" }
{ "operation": "log", "limit": 5 }
```

Additional Git operations should be added one at a time with explicit permission behavior.

## Patch Behavior

`apply_patch` should be structured and conservative:

- validate patch syntax before execution
- reject file targets outside the repo
- reject path traversal and destructive ambiguity
- surface changed files and diff summary
- follow the current guided-mode confirmation policy

The model may request a patch through the tool, but the policy decides whether it is applied immediately, staged as a proposal, or blocked pending user confirmation.

## Error Handling

Tool execution should return structured observations instead of leaking exceptions:

- `invalid_args`: Pydantic validation failed.
- `blocked`: permission policy rejected the call.
- `requires_confirmation`: user confirmation is needed before execution.
- `failed`: execution completed with an error.
- `timed_out`: execution exceeded the configured timeout.
- `success`: execution completed successfully.

Observations should include concise summaries and structured payloads where useful. Tracebacks, API keys, and excessive output should not be sent to the model.

## Context Management

Each tool should own its output formatting:

- `read_file`: file path, line range, size metadata, and content excerpt.
- `list_dir`: path, entry count, and bounded entry list.
- `glob_file_search`: pattern, match count, and bounded path list.
- `rg`: query, match count, file paths, line numbers, and bounded match excerpts.
- `git`: operation, exit status, changed files, stats, or log excerpt.
- `apply_patch`: applied/proposed/blocked status, changed files, and summary.
- `run_shell_command`: command, cwd, exit code, duration, and stdout/stderr excerpts.

Output truncation is part of the tool contract, not an afterthought in the provider prompt.

## Compatibility

The existing JSON Action path can remain for scripted tests and non-native fallback:

```text
JSON action -> ToolInvocation(source="json_action") -> registry execution
```

However, because the current product setup uses an OpenAI-protocol API, the native `tool_calls` path is the primary design target.

## Testing

Tests should be written before implementation.

Required coverage:

- Registry returns expected tool names.
- Each `ToolSpec` can generate valid OpenAI-compatible JSON Schema.
- Pydantic args validation rejects malformed tool calls.
- OpenAI provider converts native `tool_calls` into `ToolInvocation` objects.
- Tool observations convert back into `role="tool"` messages with matching IDs.
- `read_file`, `list_dir`, `glob_file_search`, `rg`, and safe `git` operations run as read-only tools.
- unsafe Git operations are blocked or require confirmation according to policy.
- `apply_patch` rejects repo-escaping targets.
- `run_shell_command` still delegates to shell policy.
- `run_command` remains verification-only.
- Agent loop can process a model response with one tool call and continue.
- Agent loop can process multiple returned tool calls sequentially.
- Invalid args become observations rather than uncaught exceptions.

Full verification:

```bash
PYTHONPATH=. uv run --isolated --python 3.12 --with-requirements requirements.txt python -m pytest -q
PYTHONPATH=. uv run --isolated --python 3.12 --with-requirements requirements.txt python -m ruff check .
```

## Documentation Updates

After implementation and verification, update:

- `MendCode_开发方案.md`
- `MendCode_全局路线图.md`
- `MendCode_TUI产品基调与交互方案.md`
- provider configuration docs if native tool calling becomes user-visible

Only mark roadmap items complete after tests and lint pass.

## Acceptance Criteria

- OpenAI-compatible provider can send native `tools` generated from `ToolRegistry`.
- Native OpenAI `tool_calls` are normalized into internal `ToolInvocation` objects.
- Tool results are returned to the model as proper OpenAI `role="tool"` messages.
- Agent loop stays independent of raw OpenAI message shapes.
- Tool args are validated with Pydantic before execution.
- Tool risk and permission decisions are explicit and tested.
- Structured read-only tools are preferred over raw shell commands.
- Existing JSON Action fallback remains usable for tests or transition.
- No API key, excessive output, or unbounded file content is exposed in observations.
- Full pytest and ruff verification passes.
