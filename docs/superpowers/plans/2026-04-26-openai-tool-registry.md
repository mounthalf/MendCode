# OpenAI Tool Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Hybrid ToolRegistry so OpenAI-protocol models can use native `tool_calls` while MendCode keeps a provider-neutral execution and permission model.

**Architecture:** A central registry owns tool specs, Pydantic argument schemas, OpenAI schema generation, execution dispatch, permission metadata, and observation formatting. The OpenAI-compatible provider converts native tool calls into internal `ToolInvocation` objects; the Agent loop executes those invocations through the registry and still preserves the existing JSON Action fallback.

**Tech Stack:** Python 3.12, Pydantic 2, OpenAI chat completions API, pytest, ruff.

---

## File Structure

- Create `app/tools/structured.py`
  - Generic tool primitives: `ToolRisk`, `ToolInvocation`, `ToolExecutionContext`, `ToolSpec`, `ToolRegistry`.
  - OpenAI `tools` schema generation from Pydantic args models.

- Create `app/tools/arguments.py`
  - Pydantic args models for `read_file`, `list_dir`, `glob_file_search`, `rg`, `git`, `apply_patch`, `run_shell_command`, and `run_command`.

- Create `app/tools/registry.py`
  - Default registry wiring.
  - Tool executors that call existing file, search, patch, shell, git, and verification helpers.
  - Tool result to `Observation` conversion and bounded output formatting.

- Modify `app/tools/__init__.py`
  - Export registry primitives and `default_tool_registry`.

- Modify `app/agent/provider.py`
  - Extend `AgentObservationRecord` to optionally carry `ToolInvocation`.
  - Extend `ProviderResponse` to support native `tool_invocations` as an alternative to JSON actions.

- Modify `app/agent/openai_compatible.py`
  - Change the client boundary from text-only completion to structured completion with optional native tool calls.
  - Send OpenAI `tools` generated from `ToolRegistry`.
  - Parse native tool calls into `ToolInvocation`.
  - Preserve JSON Action fallback for assistant text.

- Modify `app/agent/prompt_context.py`
  - Allow OpenAI chat messages with `tool_calls` and `tool_call_id`.
  - Convert native tool observations into `role="tool"` messages.
  - Keep JSON Action fallback prompt behavior.

- Modify `app/agent/loop.py`
  - Route JSON Action tool calls through the registry.
  - Execute native provider tool invocations sequentially.
  - Record native invocations in observation history.
  - Preserve final-response verification gating.

- Modify `app/agent/permission.py`
  - Source risk levels from the registry where practical.
  - Keep current guided/safe/full/custom behavior.

- Add or modify tests:
  - `tests/unit/test_tool_registry.py`
  - `tests/unit/test_openai_compatible_provider.py`
  - `tests/unit/test_prompt_context.py`
  - `tests/unit/test_agent_loop.py`
  - `tests/unit/test_permission_gate.py`

---

### Task 1: Add ToolRegistry Primitives

**Files:**
- Create: `app/tools/structured.py`
- Modify: `app/tools/__init__.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing registry primitive tests**

Add `tests/unit/test_tool_registry.py` with:

```python
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
import pytest

from app.config.settings import Settings
from app.schemas.agent_action import Observation
from app.tools.structured import (
    ToolExecutionContext,
    ToolInvocation,
    ToolRegistry,
    ToolRisk,
    ToolSpec,
)


class ExampleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    max_chars: int = Field(default=2000, ge=0)


def execute_example(args: ExampleArgs, context: ToolExecutionContext) -> Observation:
    return Observation(
        status="succeeded",
        summary=f"Read {args.path}",
        payload={"workspace": str(context.workspace_path), "max_chars": args.max_chars},
    )


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        app_name="MendCode",
        app_version="0.0.0",
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        traces_dir=tmp_path / "data" / "traces",
        workspace_root=tmp_path / ".worktrees",
        verification_timeout_seconds=60,
        cleanup_success_workspace=False,
    )


def test_tool_spec_validates_args_and_executes(tmp_path: Path) -> None:
    spec = ToolSpec(
        name="example",
        description="Read an example path.",
        args_model=ExampleArgs,
        risk_level=ToolRisk.READ_ONLY,
        executor=execute_example,
    )
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = spec.execute({"path": "README.md"}, context)

    assert observation.status == "succeeded"
    assert observation.payload == {"workspace": str(tmp_path), "max_chars": 2000}


def test_tool_spec_rejects_invalid_args(tmp_path: Path) -> None:
    spec = ToolSpec(
        name="example",
        description="Read an example path.",
        args_model=ExampleArgs,
        risk_level=ToolRisk.READ_ONLY,
        executor=execute_example,
    )
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = spec.execute({"path": "README.md", "max_chars": -1}, context)

    assert observation.status == "rejected"
    assert observation.summary == "Invalid tool arguments"
    assert "greater than or equal to 0" in str(observation.error_message)


def test_tool_spec_generates_openai_tool_schema() -> None:
    spec = ToolSpec(
        name="example",
        description="Read an example path.",
        args_model=ExampleArgs,
        risk_level=ToolRisk.READ_ONLY,
        executor=execute_example,
    )

    assert spec.to_openai_tool()["function"]["name"] == "example"
    assert spec.to_openai_tool()["function"]["parameters"]["type"] == "object"
    assert "path" in spec.to_openai_tool()["function"]["parameters"]["properties"]


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(
        name="example",
        description="Read an example path.",
        args_model=ExampleArgs,
        risk_level=ToolRisk.READ_ONLY,
        executor=execute_example,
    )

    registry.register(spec)

    with pytest.raises(ValueError, match="duplicate tool name: example"):
        registry.register(spec)


def test_tool_invocation_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(id=None, name="", args={}, source="json_action")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py -q
```

Expected: FAIL because `app.tools.structured` does not exist.

- [ ] **Step 3: Implement `app/tools/structured.py`**

Create the file with:

```python
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config.settings import Settings
from app.schemas.agent_action import Observation


ToolInvocationSource = Literal["openai_tool_call", "json_action"]


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    WRITE_WORKTREE = "write_worktree"
    SHELL_RESTRICTED = "shell_restricted"
    DANGEROUS = "dangerous"


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    source: ToolInvocationSource
    group_id: str | None = None

    @model_validator(mode="after")
    def validate_name(self) -> "ToolInvocation":
        if not self.name.strip():
            raise ValueError("tool invocation name must not be empty")
        return self


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    workspace_path: Path
    settings: Settings
    verification_commands: list[str] = Field(default_factory=list)


ToolExecutor = Callable[[BaseModel, ToolExecutionContext], Observation]


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str
    description: str
    args_model: type[BaseModel]
    risk_level: ToolRisk
    executor: ToolExecutor

    @model_validator(mode="after")
    def validate_spec(self) -> "ToolSpec":
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        return self

    def execute(self, args: dict[str, Any], context: ToolExecutionContext) -> Observation:
        try:
            parsed_args = self.args_model.model_validate(args)
        except ValidationError as exc:
            return Observation(
                status="rejected",
                summary="Invalid tool arguments",
                payload={"tool_name": self.name, "args": args},
                error_message=str(exc),
            )
        return self.executor(parsed_args, context)

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._specs)

    def openai_tools(self) -> list[dict[str, object]]:
        return [self._specs[name].to_openai_tool() for name in self.names()]
```

- [ ] **Step 4: Export primitives**

Modify `app/tools/__init__.py` so it contains:

```python
"""Tool schema and registry exports."""

from app.tools.schemas import ToolResult, ToolStatus
from app.tools.structured import (
    ToolExecutionContext,
    ToolInvocation,
    ToolRegistry,
    ToolRisk,
    ToolSpec,
)

__all__ = [
    "ToolExecutionContext",
    "ToolInvocation",
    "ToolRegistry",
    "ToolResult",
    "ToolRisk",
    "ToolSpec",
    "ToolStatus",
]
```

- [ ] **Step 5: Run the primitive tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/tools/structured.py app/tools/__init__.py tests/unit/test_tool_registry.py
git commit -m "feat: add structured tool registry primitives"
```

---

### Task 2: Add Args Models and Register Read-Only Tools

**Files:**
- Create: `app/tools/arguments.py`
- Create: `app/tools/registry.py`
- Modify: `app/tools/__init__.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Add failing tests for default registry and read-only execution**

Append to `tests/unit/test_tool_registry.py`:

```python
from app.tools.registry import default_tool_registry


def test_default_registry_contains_read_only_tools() -> None:
    registry = default_tool_registry()

    assert registry.names()[:4] == ["glob_file_search", "list_dir", "read_file", "rg"]


def test_default_registry_generates_openai_schemas() -> None:
    registry = default_tool_registry()

    tools = registry.openai_tools()

    names = [tool["function"]["name"] for tool in tools]
    assert "read_file" in names
    read_file_schema = next(tool for tool in tools if tool["function"]["name"] == "read_file")
    assert "path" in read_file_schema["function"]["parameters"]["properties"]


def test_registry_executes_read_file_tool(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = registry.get("read_file").execute({"path": "README.md"}, context)

    assert observation.status == "succeeded"
    assert observation.payload["relative_path"] == "README.md"
    assert observation.payload["content"] == "hello\n"


def test_registry_rejects_bad_read_file_args(tmp_path: Path) -> None:
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = registry.get("read_file").execute({"path": "README.md", "max_chars": -1}, context)

    assert observation.status == "rejected"
    assert observation.summary == "Invalid tool arguments"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py -q
```

Expected: FAIL because `app.tools.registry` and `app.tools.arguments` do not exist.

- [ ] **Step 3: Implement args models**

Create `app/tools/arguments.py` with:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Repo-relative file path to read.")
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    max_chars: int | None = Field(default=12000, ge=0)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ReadFileArgs":
        if self.start_line is not None and self.end_line is not None and self.start_line > self.end_line:
            raise ValueError("start_line cannot be greater than end_line")
        return self


class ListDirArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(default=".", description="Repo-relative directory path to list.")
    max_entries: int | None = Field(default=200, ge=0)


class GlobFileSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(description="Repo-relative glob pattern such as '**/*.py'.")
    max_results: int | None = Field(default=200, ge=0)


class RgArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Text to search for.")
    glob: str | None = Field(default=None, description="Optional ripgrep glob filter.")
    max_results: int | None = Field(default=50, ge=0)


class GitArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["status", "diff", "log"]
    path: str | None = None
    limit: int = Field(default=5, ge=1, le=50)


class ApplyPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: str
    files_to_modify: list[str] = Field(default_factory=list)


class RunShellCommandArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str


class RunCommandArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
```

- [ ] **Step 4: Implement read-only registry execution**

Create `app/tools/registry.py` with:

```python
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from app.schemas.agent_action import Observation
from app.tools.arguments import (
    ApplyPatchArgs,
    GitArgs,
    GlobFileSearchArgs,
    ListDirArgs,
    ReadFileArgs,
    RgArgs,
    RunCommandArgs,
    RunShellCommandArgs,
)
from app.tools.read_only import glob_file_search, list_dir, read_file, search_code
from app.tools.schemas import ToolResult
from app.tools.structured import ToolExecutionContext, ToolRegistry, ToolRisk, ToolSpec


def tool_result_to_observation(result: ToolResult) -> Observation:
    status = "succeeded" if result.status == "passed" else result.status
    return Observation(
        status=status,
        summary=result.summary,
        payload=result.payload,
        error_message=result.error_message,
    )


def _read_file(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(ReadFileArgs, args)
    return tool_result_to_observation(
        read_file(
            workspace_path=context.workspace_path,
            relative_path=parsed.path,
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            max_chars=parsed.max_chars,
        )
    )


def _list_dir(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(ListDirArgs, args)
    return tool_result_to_observation(
        list_dir(
            workspace_path=context.workspace_path,
            relative_path=parsed.path,
            max_entries=parsed.max_entries,
        )
    )


def _glob_file_search(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(GlobFileSearchArgs, args)
    return tool_result_to_observation(
        glob_file_search(
            workspace_path=context.workspace_path,
            pattern=parsed.pattern,
            max_results=parsed.max_results,
        )
    )


def _rg(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(RgArgs, args)
    return tool_result_to_observation(
        search_code(
            workspace_path=context.workspace_path,
            query=parsed.query,
            glob=parsed.glob,
            max_results=parsed.max_results,
        )
    )


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read bounded UTF-8 text from a repo-relative file path.",
            args_model=ReadFileArgs,
            risk_level=ToolRisk.READ_ONLY,
            executor=_read_file,
        )
    )
    registry.register(
        ToolSpec(
            name="list_dir",
            description="List entries in a repo-relative directory.",
            args_model=ListDirArgs,
            risk_level=ToolRisk.READ_ONLY,
            executor=_list_dir,
        )
    )
    registry.register(
        ToolSpec(
            name="glob_file_search",
            description="Find repo files matching a relative glob pattern.",
            args_model=GlobFileSearchArgs,
            risk_level=ToolRisk.READ_ONLY,
            executor=_glob_file_search,
        )
    )
    registry.register(
        ToolSpec(
            name="rg",
            description="Search repo text using a bounded ripgrep-style query.",
            args_model=RgArgs,
            risk_level=ToolRisk.READ_ONLY,
            executor=_rg,
        )
    )
    return registry
```

Remove the unused `Path`, `ApplyPatchArgs`, `GitArgs`, `RunCommandArgs`, and `RunShellCommandArgs` imports before committing if ruff reports them.

- [ ] **Step 5: Export the default registry**

Update `app/tools/__init__.py` imports and `__all__`:

```python
from app.tools.registry import default_tool_registry
```

and include `"default_tool_registry"` in `__all__`.

- [ ] **Step 6: Run focused tests and lint**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py tests/unit/test_read_only_tools.py -q
PYTHONPATH=. python -m ruff check app/tools tests/unit/test_tool_registry.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/tools/arguments.py app/tools/registry.py app/tools/__init__.py tests/unit/test_tool_registry.py
git commit -m "feat: register read-only structured tools"
```

---

### Task 3: Register Command, Git, Shell, and Patch Tools

**Files:**
- Modify: `app/tools/registry.py`
- Modify: `tests/unit/test_tool_registry.py`
- Test: `tests/unit/test_agent_loop.py`

- [ ] **Step 1: Add failing registry tests for command-like tools**

Append to `tests/unit/test_tool_registry.py`:

```python
import subprocess


def init_repo(path: Path) -> Path:
    repo = path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    return repo


def test_default_registry_contains_command_tools() -> None:
    registry = default_tool_registry()

    assert "git" in registry.names()
    assert "apply_patch" in registry.names()
    assert "run_shell_command" in registry.names()
    assert "run_command" in registry.names()


def test_git_status_uses_structured_operation(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=repo,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = registry.get("git").execute({"operation": "status"}, context)

    assert observation.status == "succeeded"
    assert observation.payload["command"] == "git status --short"
    assert "README.md" in observation.payload["stdout_excerpt"]


def test_git_rejects_unknown_operation_before_shell(tmp_path: Path) -> None:
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = registry.get("git").execute({"operation": "reset"}, context)

    assert observation.status == "rejected"
    assert observation.summary == "Invalid tool arguments"


def test_run_command_keeps_verification_allowlist(tmp_path: Path) -> None:
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )

    observation = registry.get("run_command").execute(
        {"command": "python -c 'print(123)'"},
        context,
    )

    assert observation.status == "rejected"
    assert "declared" in str(observation.error_message)


def test_apply_patch_rejects_repo_escaping_path(tmp_path: Path) -> None:
    registry = default_tool_registry()
    context = ToolExecutionContext(
        workspace_path=tmp_path,
        settings=settings_for(tmp_path),
        verification_commands=[],
    )
    patch = "\n".join(
        [
            "diff --git a/../outside.txt b/../outside.txt",
            "--- a/../outside.txt",
            "+++ b/../outside.txt",
            "@@ -0,0 +1 @@",
            "+bad",
            "",
        ]
    )

    observation = registry.get("apply_patch").execute({"patch": patch}, context)

    assert observation.status == "rejected"
    assert "patch path escapes workspace root" in str(observation.error_message)
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py -q
```

Expected: FAIL because these tools are not registered.

- [ ] **Step 3: Add registry executors**

Modify `app/tools/registry.py` to import existing helpers:

```python
import shlex
import shutil
import subprocess

from app.workspace.command_policy import CommandPolicy
from app.workspace.executor import execute_verification_command
from app.workspace.shell_executor import ShellCommandResult, execute_shell_command
from app.workspace.shell_policy import ShellPolicy
```

Add these functions below the read-only executors:

```python
def _failed(summary: str, message: str, payload: dict[str, object] | None = None) -> Observation:
    return Observation(status="failed", summary=summary, payload=payload or {}, error_message=message)


def _rejected(summary: str, message: str, payload: dict[str, object] | None = None) -> Observation:
    return Observation(status="rejected", summary=summary, payload=payload or {}, error_message=message)


def _shell_result_to_observation(result: ShellCommandResult) -> Observation:
    if result.status == "passed":
        status = "succeeded"
    elif result.status in {"rejected", "needs_confirmation"}:
        status = "rejected"
    else:
        status = "failed"
    return Observation(
        status=status,
        summary=f"Ran shell command: {result.command}",
        payload=result.model_dump(mode="json"),
        error_message=None if status == "succeeded" else result.stderr_excerpt,
    )


def _git_command(args: GitArgs) -> str:
    if args.operation == "status":
        return "git status --short"
    if args.operation == "diff":
        return "git diff -- " + shlex.quote(args.path) if args.path else "git diff"
    if args.operation == "log":
        return f"git log --oneline -{args.limit}"
    raise AssertionError(f"unsupported git operation: {args.operation}")


def _git(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(GitArgs, args)
    command = _git_command(parsed)
    result = execute_shell_command(
        command=command,
        cwd=context.workspace_path,
        policy=ShellPolicy(
            allowed_root=context.workspace_path,
            timeout_seconds=context.settings.verification_timeout_seconds,
        ),
    )
    return _shell_result_to_observation(result)


def _run_shell_command(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(RunShellCommandArgs, args)
    if not parsed.command.strip():
        return _rejected("Unable to run shell command", "command must not be empty", {"command": parsed.command})
    result = execute_shell_command(
        command=parsed.command,
        cwd=context.workspace_path,
        policy=ShellPolicy(
            allowed_root=context.workspace_path,
            timeout_seconds=context.settings.verification_timeout_seconds,
        ),
    )
    return _shell_result_to_observation(result)


def _run_command(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(RunCommandArgs, args)
    if not parsed.command.strip():
        return _rejected("Unable to run command", "command must not be empty", {"command": parsed.command})
    policy = CommandPolicy(
        allowed_commands=context.verification_commands,
        allowed_root=context.workspace_path,
        timeout_seconds=context.settings.verification_timeout_seconds,
    )
    result = execute_verification_command(command=parsed.command, cwd=context.workspace_path, policy=policy)
    status = "succeeded" if result.status == "passed" else result.status
    if status == "timed_out":
        status = "failed"
    return Observation(
        status=status,
        summary=f"Ran command: {parsed.command}",
        payload=result.model_dump(mode="json"),
        error_message=None if result.status == "passed" else result.stderr_excerpt,
    )


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            paths.extend(part[2:] for part in parts[2:4] if part.startswith(("a/", "b/")))
        elif line.startswith(("--- a/", "+++ b/")):
            paths.append(line.split(maxsplit=1)[1][2:])
    return [path for path in paths if path != "/dev/null"]


def _validate_patch_paths(patch: str, workspace_path: Path) -> Observation | None:
    workspace_root = workspace_path.resolve()
    for relative_path in _patch_paths(patch):
        candidate = (workspace_root / relative_path).resolve()
        try:
            candidate.relative_to(workspace_root)
        except ValueError:
            return _rejected(
                "Unable to apply patch",
                "patch path escapes workspace root",
                {"relative_path": relative_path},
            )
    return None


def _apply_patch(args: BaseModel, context: ToolExecutionContext) -> Observation:
    parsed = cast(ApplyPatchArgs, args)
    if not parsed.patch.strip():
        return _rejected("Unable to apply patch", "patch must not be empty")
    path_observation = _validate_patch_paths(parsed.patch, context.workspace_path)
    if path_observation is not None:
        return path_observation
    try:
        completed = subprocess.run(
            ["git", "apply", "--whitespace=nowarn"],
            cwd=context.workspace_path,
            input=parsed.patch,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return _failed("Unable to apply patch", str(exc))
    if completed.returncode != 0:
        return _failed(
            "Unable to apply patch",
            completed.stderr or completed.stdout or "git apply failed",
            {"files_to_modify": parsed.files_to_modify, "stderr": completed.stderr, "stdout": completed.stdout},
        )
    for pycache_path in context.workspace_path.rglob("__pycache__"):
        if pycache_path.is_dir():
            shutil.rmtree(pycache_path, ignore_errors=True)
    return Observation(
        status="succeeded",
        summary="Applied patch",
        payload={"files_to_modify": parsed.files_to_modify or _patch_paths(parsed.patch)},
    )
```

Register these specs in `default_tool_registry()`:

```python
    registry.register(
        ToolSpec(
            name="git",
            description="Run a safe structured Git inspection operation: status, diff, or log.",
            args_model=GitArgs,
            risk_level=ToolRisk.READ_ONLY,
            executor=_git,
        )
    )
    registry.register(
        ToolSpec(
            name="run_shell_command",
            description="Run a shell command through MendCode's restricted shell policy.",
            args_model=RunShellCommandArgs,
            risk_level=ToolRisk.SHELL_RESTRICTED,
            executor=_run_shell_command,
        )
    )
    registry.register(
        ToolSpec(
            name="run_command",
            description="Run one declared verification command.",
            args_model=RunCommandArgs,
            risk_level=ToolRisk.SHELL_RESTRICTED,
            executor=_run_command,
        )
    )
    registry.register(
        ToolSpec(
            name="apply_patch",
            description="Apply a unified diff patch inside the current workspace after path validation.",
            args_model=ApplyPatchArgs,
            risk_level=ToolRisk.WRITE_WORKTREE,
            executor=_apply_patch,
        )
    )
```

- [ ] **Step 4: Run focused tests and lint**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_tool_registry.py tests/unit/test_shell_policy.py tests/unit/test_shell_executor.py -q
PYTHONPATH=. python -m ruff check app/tools tests/unit/test_tool_registry.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/tools/registry.py tests/unit/test_tool_registry.py
git commit -m "feat: register structured command tools"
```

---

### Task 4: Extend ProviderResponse for Native Tool Invocations

**Files:**
- Modify: `app/agent/provider.py`
- Test: `tests/unit/test_agent_provider.py`

- [ ] **Step 1: Add failing provider response tests**

Append to `tests/unit/test_agent_provider.py`:

```python
from app.tools.structured import ToolInvocation


def test_provider_response_accepts_native_tool_invocations() -> None:
    response = ProviderResponse(
        status="succeeded",
        tool_invocations=[
            ToolInvocation(
                id="call_1",
                name="read_file",
                args={"path": "README.md"},
                source="openai_tool_call",
            )
        ],
    )

    assert response.tool_invocations[0].name == "read_file"
    assert response.actions == []


def test_provider_response_rejects_actions_and_tool_invocations_together() -> None:
    with pytest.raises(ValueError, match="must not mix actions and tool invocations"):
        ProviderResponse(
            status="succeeded",
            actions=[{"type": "final_response", "status": "completed", "summary": "done"}],
            tool_invocations=[
                ToolInvocation(
                    id="call_1",
                    name="read_file",
                    args={"path": "README.md"},
                    source="openai_tool_call",
                )
            ],
        )
```

If `pytest` is not imported in `tests/unit/test_agent_provider.py`, add `import pytest`.

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_agent_provider.py -q
```

Expected: FAIL because `ProviderResponse` has no `tool_invocations`.

- [ ] **Step 3: Update provider models**

Modify imports in `app/agent/provider.py`:

```python
from app.tools.structured import ToolInvocation
```

Change `AgentObservationRecord`:

```python
class AgentObservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MendCodeAction | None = None
    tool_invocation: ToolInvocation | None = None
    observation: Observation
```

Change `ProviderResponse`:

```python
class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProviderStatus
    actions: list[dict[str, object]] = Field(default_factory=list)
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    observation: Observation | None = None

    @property
    def action(self) -> dict[str, object] | None:
        return self.actions[0] if self.actions else None

    @classmethod
    def failed(cls, error_message: str) -> "ProviderResponse":
        return cls(
            status="failed",
            observation=Observation(
                status="failed",
                summary="Provider failed",
                payload={},
                error_message=error_message,
            ),
        )

    @model_validator(mode="after")
    def validate_response_shape(self) -> "ProviderResponse":
        if self.status == "succeeded":
            if bool(self.actions) == bool(self.tool_invocations):
                raise ValueError("succeeded provider responses require either actions or tool invocations")
            if self.actions and self.tool_invocations:
                raise ValueError("provider responses must not mix actions and tool invocations")
        if self.status == "failed" and self.observation is None:
            raise ValueError("failed provider responses require observation")
        return self
```

If the first `if` makes the second mixed-action branch unreachable, rewrite the succeeded branch as:

```python
        if self.status == "succeeded":
            if self.actions and self.tool_invocations:
                raise ValueError("provider responses must not mix actions and tool invocations")
            if not self.actions and not self.tool_invocations:
                raise ValueError("succeeded provider responses require either actions or tool invocations")
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_agent_provider.py -q
PYTHONPATH=. python -m ruff check app/agent/provider.py tests/unit/test_agent_provider.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agent/provider.py tests/unit/test_agent_provider.py
git commit -m "feat: allow provider tool invocations"
```

---

### Task 5: Add OpenAI Native Tool Call Provider Support

**Files:**
- Modify: `app/agent/openai_compatible.py`
- Modify: `tests/unit/test_openai_compatible_provider.py`

- [ ] **Step 1: Add failing native tool call tests**

Modify the fake client in `tests/unit/test_openai_compatible_provider.py` so it can return structured results:

```python
class FakeClient:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict[str, object]] = []
```

Append these tests:

```python
from app.agent.openai_compatible import OpenAICompletion, OpenAIToolCall
from app.tools.registry import default_tool_registry


def test_openai_provider_sends_registered_tools() -> None:
    client = FakeClient(
        OpenAICompletion(
            content='{"type":"final_response","status":"completed","summary":"done"}',
            tool_calls=[],
        )
    )
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=client,
        tool_registry=default_tool_registry(),
    )

    provider.next_action(step_input())

    tools = client.calls[0]["tools"]
    assert isinstance(tools, list)
    assert any(tool["function"]["name"] == "read_file" for tool in tools)


def test_openai_provider_returns_native_tool_invocations() -> None:
    client = FakeClient(
        OpenAICompletion(
            content="",
            tool_calls=[
                OpenAIToolCall(
                    id="call_1",
                    name="read_file",
                    arguments='{"path":"README.md"}',
                )
            ],
        )
    )
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=client,
        tool_registry=default_tool_registry(),
    )

    response = provider.next_action(step_input())

    assert response.status == "succeeded"
    assert response.tool_invocations[0].id == "call_1"
    assert response.tool_invocations[0].name == "read_file"
    assert response.tool_invocations[0].args == {"path": "README.md"}


def test_openai_provider_rejects_invalid_tool_arguments_json() -> None:
    client = FakeClient(
        OpenAICompletion(
            content="",
            tool_calls=[
                OpenAIToolCall(
                    id="call_1",
                    name="read_file",
                    arguments="{not-json",
                )
            ],
        )
    )
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=client,
        tool_registry=default_tool_registry(),
    )

    response = provider.next_action(step_input())

    assert response.status == "failed"
    assert response.observation is not None
    assert response.observation.error_message == "Provider returned invalid tool call arguments"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_openai_compatible_provider.py -q
```

Expected: FAIL because `OpenAICompletion`, `OpenAIToolCall`, and `tool_registry` support do not exist.

- [ ] **Step 3: Implement structured completion models and client protocol**

In `app/agent/openai_compatible.py`, add imports:

```python
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import default_tool_registry
from app.tools.structured import ToolInvocation, ToolRegistry
```

Add models above `OpenAICompatibleClient`:

```python
class OpenAIToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: str


class OpenAICompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = ""
    tool_calls: list[OpenAIToolCall] = Field(default_factory=list)
```

Change the protocol:

```python
class OpenAICompatibleClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, object]],
        timeout_seconds: int,
    ) -> OpenAICompletion:
        raise NotImplementedError
```

Change `OpenAIChatCompletionsClient.complete()` to pass tools and return `OpenAICompletion`:

```python
        response = self._client.chat.completions.create(
            model=model,
            messages=[message.model_dump(exclude_none=True) for message in messages],
            tools=tools,
            timeout=timeout_seconds,
        )
        message = response.choices[0].message
        tool_calls = []
        for tool_call in message.tool_calls or []:
            tool_calls.append(
                OpenAIToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )
        return OpenAICompletion(content=message.content or "", tool_calls=tool_calls)
```

- [ ] **Step 4: Parse native tool calls in provider**

Update `OpenAICompatibleAgentProvider.__init__`:

```python
        tool_registry: ToolRegistry | None = None,
```

and assign:

```python
        self._tool_registry = tool_registry or default_tool_registry()
```

Update `next_action()`:

```python
            completion = self._client.complete(
                model=self._model,
                messages=build_provider_messages(step_input, secret_values=[self._api_key]),
                tools=self._tool_registry.openai_tools(),
                timeout_seconds=self._timeout_seconds,
            )
```

Then handle native tool calls before text JSON:

```python
        if completion.tool_calls:
            invocations: list[ToolInvocation] = []
            for tool_call in completion.tool_calls:
                try:
                    parsed_args = json.loads(tool_call.arguments or "{}")
                except json.JSONDecodeError:
                    return ProviderResponse.failed("Provider returned invalid tool call arguments")
                if not isinstance(parsed_args, dict):
                    return ProviderResponse.failed("Provider returned non-object tool call arguments")
                invocations.append(
                    ToolInvocation(
                        id=tool_call.id,
                        name=tool_call.name,
                        args=parsed_args,
                        source="openai_tool_call",
                    )
                )
            return ProviderResponse(status="succeeded", tool_invocations=invocations)

        content = completion.content
```

Keep the existing JSON parsing path after this block.

- [ ] **Step 5: Update existing FakeClient calls**

In `tests/unit/test_openai_compatible_provider.py`, change `FakeClient.complete()` signature to accept `tools`, record it, and return `OpenAICompletion`:

```python
    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, object]],
        timeout_seconds: int,
    ) -> OpenAICompletion:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.exc is not None:
            raise self.exc
        if isinstance(self.response, OpenAICompletion):
            return self.response
        return OpenAICompletion(content=str(self.response or ""), tool_calls=[])
```

- [ ] **Step 6: Run provider tests and lint**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_openai_compatible_provider.py tests/unit/test_provider_factory.py -q
PYTHONPATH=. python -m ruff check app/agent/openai_compatible.py tests/unit/test_openai_compatible_provider.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/agent/openai_compatible.py tests/unit/test_openai_compatible_provider.py
git commit -m "feat: parse openai native tool calls"
```

---

### Task 6: Return Native Tool Results as OpenAI Tool Messages

**Files:**
- Modify: `app/agent/prompt_context.py`
- Modify: `tests/unit/test_prompt_context.py`

- [ ] **Step 1: Add failing prompt context tests**

Append to `tests/unit/test_prompt_context.py`:

```python
from app.schemas.agent_action import Observation
from app.tools.structured import ToolInvocation


def test_provider_messages_include_openai_tool_result_messages() -> None:
    messages = build_provider_messages(
        AgentProviderStepInput(
            problem_statement="inspect",
            verification_commands=[],
            step_index=2,
            remaining_steps=4,
            observations=[
                AgentObservationRecord(
                    tool_invocation=ToolInvocation(
                        id="call_1",
                        name="read_file",
                        args={"path": "README.md"},
                        source="openai_tool_call",
                        group_id="provider-1",
                    ),
                    observation=Observation(
                        status="succeeded",
                        summary="Read README.md",
                        payload={"relative_path": "README.md", "content": "hello"},
                    ),
                )
            ],
        )
    )

    assert messages[-2].role == "assistant"
    assert messages[-2].tool_calls[0].id == "call_1"
    assert messages[-1].role == "tool"
    assert messages[-1].tool_call_id == "call_1"
    assert "Read README.md" in messages[-1].content
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_prompt_context.py -q
```

Expected: FAIL because `ChatMessage` does not support `tool_calls` or `tool_call_id`.

- [ ] **Step 3: Extend chat message models**

In `app/agent/prompt_context.py`, add these models above `ChatMessage`:

```python
class ChatToolFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: str


class ChatToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "function"
    function: ChatToolFunction
```

Change `ChatMessage`:

```python
class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str | None = None
    tool_calls: list[ChatToolCall] | None = None
    tool_call_id: str | None = None
```

- [ ] **Step 4: Add native tool message helpers**

In `app/agent/prompt_context.py`, import `ToolInvocation` and add:

```python
def _tool_result_content(
    record: AgentObservationRecord,
    *,
    limits: PromptContextLimits,
    secret_values: list[str],
) -> str:
    return json.dumps(
        summarize_observation_record(
            record,
            limits=limits,
            secret_values=secret_values,
        ),
        ensure_ascii=False,
        sort_keys=True,
    )


def _tool_call_message(invocations: list[ToolInvocation]) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ChatToolCall(
                id=invocation.id or invocation.name,
                function=ChatToolFunction(
                    name=invocation.name,
                    arguments=json.dumps(invocation.args, ensure_ascii=False, sort_keys=True),
                ),
            )
            for invocation in invocations
        ],
    )
```

At the end of `build_provider_messages()`, before returning, build `base_messages` for the existing system and user messages. Then append native tool message pairs:

```python
    messages = [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(
            role="user",
            content=json.dumps(user_context, ensure_ascii=False, sort_keys=True),
        ),
    ]
    native_records = [
        record
        for record in step_input.observations[-context_limits.max_observations :]
        if record.tool_invocation is not None and record.tool_invocation.id is not None
    ]
    grouped: dict[str, list[AgentObservationRecord]] = {}
    for record in native_records:
        assert record.tool_invocation is not None
        group_id = record.tool_invocation.group_id or record.tool_invocation.id or record.tool_invocation.name
        grouped.setdefault(group_id, []).append(record)
    for records in grouped.values():
        invocations = [record.tool_invocation for record in records if record.tool_invocation is not None]
        messages.append(_tool_call_message(invocations))
        for record in records:
            assert record.tool_invocation is not None
            messages.append(
                ChatMessage(
                    role="tool",
                    tool_call_id=record.tool_invocation.id,
                    content=_tool_result_content(
                        record,
                        limits=context_limits,
                        secret_values=secrets,
                    ),
                )
            )
    return messages
```

Remove the old direct list return.

- [ ] **Step 5: Run prompt tests and lint**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_prompt_context.py tests/unit/test_openai_compatible_provider.py -q
PYTHONPATH=. python -m ruff check app/agent/prompt_context.py tests/unit/test_prompt_context.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/agent/prompt_context.py tests/unit/test_prompt_context.py
git commit -m "feat: build openai tool result messages"
```

---

### Task 7: Execute Native Tool Invocations in AgentLoop

**Files:**
- Modify: `app/agent/loop.py`
- Modify: `tests/unit/test_agent_loop.py`
- Modify: `tests/unit/test_permission_gate.py`

- [ ] **Step 1: Add failing loop tests for native tool invocations**

Append to `tests/unit/test_agent_loop.py`:

```python
from app.tools.structured import ToolInvocation


class NativeToolProvider:
    def __init__(self, batches: list[list[ToolInvocation] | dict[str, object]]) -> None:
        self.batches = batches
        self.calls: list[AgentProviderStepInput] = []

    def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
        self.calls.append(step_input)
        index = len(self.calls) - 1
        batch = self.batches[index]
        if isinstance(batch, dict):
            return ProviderResponse(status="succeeded", actions=[batch])
        return ProviderResponse(status="succeeded", tool_invocations=batch)


def test_agent_loop_executes_native_tool_invocation(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    provider = NativeToolProvider(
        [
            [
                ToolInvocation(
                    id="call_1",
                    name="read_file",
                    args={"path": "README.md"},
                    source="openai_tool_call",
                )
            ],
            {"type": "final_response", "status": "completed", "summary": "done"},
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="read file",
            provider=provider,
            step_budget=4,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "completed"
    assert result.steps[0].observation.status == "succeeded"
    assert provider.calls[1].observations[0].tool_invocation is not None
    assert provider.calls[1].observations[0].tool_invocation.id == "call_1"


def test_agent_loop_executes_multiple_native_tool_invocations_sequentially(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("notes\n", encoding="utf-8")
    provider = NativeToolProvider(
        [
            [
                ToolInvocation(
                    id="call_1",
                    name="read_file",
                    args={"path": "README.md"},
                    source="openai_tool_call",
                ),
                ToolInvocation(
                    id="call_2",
                    name="read_file",
                    args={"path": "notes.txt"},
                    source="openai_tool_call",
                ),
            ],
            {"type": "final_response", "status": "completed", "summary": "done"},
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="read files",
            provider=provider,
            step_budget=5,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "completed"
    assert [step.observation.status for step in result.steps[:2]] == ["succeeded", "succeeded"]
    assert provider.calls[1].observations[0].tool_invocation.group_id == "provider-1"
    assert provider.calls[1].observations[1].tool_invocation.group_id == "provider-1"


def test_agent_loop_rejects_unknown_native_tool(tmp_path: Path) -> None:
    provider = NativeToolProvider(
        [
            [
                ToolInvocation(
                    id="call_1",
                    name="delete_repo",
                    args={},
                    source="openai_tool_call",
                )
            ]
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="bad tool",
            provider=provider,
            step_budget=2,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.steps[0].observation.status == "rejected"
    assert "unknown tool: delete_repo" in str(result.steps[0].observation.error_message)
```

- [ ] **Step 2: Run failing loop tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_agent_loop.py::test_agent_loop_executes_native_tool_invocation tests/unit/test_agent_loop.py::test_agent_loop_executes_multiple_native_tool_invocations_sequentially tests/unit/test_agent_loop.py::test_agent_loop_rejects_unknown_native_tool -q
```

Expected: FAIL because the loop does not consume `tool_invocations`.

- [ ] **Step 3: Refactor JSON tool execution through registry**

In `app/agent/loop.py`, import registry types:

```python
from app.tools.registry import default_tool_registry
from app.tools.structured import ToolExecutionContext, ToolInvocation
```

Add:

```python
def _tool_call_action_to_invocation(action: ToolCallAction) -> ToolInvocation:
    return ToolInvocation(
        id=None,
        name=action.action,
        args=action.args,
        source="json_action",
    )


def _invocation_to_tool_call_action(invocation: ToolInvocation) -> ToolCallAction:
    return ToolCallAction(
        type="tool_call",
        action=invocation.name,  # type: ignore[arg-type]
        reason=f"model called tool {invocation.name}",
        args=invocation.args,
    )


def _execute_tool_invocation(
    *,
    invocation: ToolInvocation,
    repo_path: Path,
    settings: Settings,
    verification_commands: list[str],
) -> Observation:
    registry = default_tool_registry()
    try:
        spec = registry.get(invocation.name)
    except KeyError as exc:
        return Observation(
            status="rejected",
            summary="Unsupported tool",
            payload=invocation.model_dump(mode="json"),
            error_message=str(exc),
        )
    return spec.execute(
        invocation.args,
        ToolExecutionContext(
            workspace_path=repo_path,
            settings=settings,
            verification_commands=verification_commands,
        ),
    )
```

Change `_execute_tool_call()` to:

```python
def _execute_tool_call(
    *,
    action: ToolCallAction,
    repo_path: Path,
    settings: Settings,
    verification_commands: list[str],
) -> Observation:
    if action.action == "repo_status":
        return _repo_status(repo_path)
    if action.action == "detect_project":
        return _detect_project(repo_path)
    if action.action == "show_diff":
        return _show_diff(repo_path)
    if action.action in {"search_code", "apply_patch_to_worktree"}:
        # Keep transitional compatibility for legacy scripted actions.
        pass
    if action.action == "search_code":
        result = search_code(
            workspace_path=repo_path,
            query=str(action.args.get("query", "")),
            glob=action.args.get("glob"),  # type: ignore[arg-type]
            max_results=action.args.get("max_results"),  # type: ignore[arg-type]
        )
        return _tool_result_to_observation(result)
    if action.action == "apply_patch_to_worktree":
        result = apply_patch(
            workspace_path=repo_path,
            relative_path=str(action.args.get("relative_path", "")),
            target_text=str(action.args.get("target_text", "")),
            replacement_text=str(action.args.get("replacement_text", "")),
            replace_all=bool(action.args.get("replace_all", False)),
        )
        return _tool_result_to_observation(result)
    return _execute_tool_invocation(
        invocation=_tool_call_action_to_invocation(action),
        repo_path=repo_path,
        settings=settings,
        verification_commands=verification_commands,
    )
```

After this change, delete old `_run_command`, `_run_shell_command`, `_run_git`, `_run_rg`, `_apply_patch_tool`, and helpers that are only used by the old dispatch. Keep helpers still needed by `repo_status`, `detect_project`, `show_diff`, patch proposal, and transitional tools.

- [ ] **Step 4: Add native invocation handling in provider loop**

Add two small helper builders before `run_agent_loop()`:

```python
def _provider_failure_handled(
    *,
    provider_response: ProviderResponse,
    index: int,
) -> _HandledAction:
    observation = provider_response.observation or _failed_observation(
        "Provider failed",
        "provider failed without observation",
    )
    action = FinalResponseAction(
        type="final_response",
        status="failed",
        summary="Provider failed",
    )
    return _HandledAction(
        stop=True,
        status="failed",
        summary=observation.summary,
        step=AgentStep(index=index, action=action, observation=observation),
    )


def _invalid_provider_actions_handled(
    *,
    actions: list[dict[str, object]],
    index: int,
) -> _HandledAction:
    observation = build_invalid_action_observation(
        payload={"actions": actions},
        error_message="provider step responses must include exactly one action",
    )
    action = FinalResponseAction(
        type="final_response",
        status="failed",
        summary="Invalid MendCode action",
    )
    return _HandledAction(
        stop=True,
        status="failed",
        summary=observation.summary,
        step=AgentStep(index=index, action=action, observation=observation),
    )
```

Replace the provider loop that currently uses `range` with a `while` that tracks action step count and provider turn count:

```python
    if loop_input.provider is not None:
        next_step_index = 1
        provider_turn_index = 1
        while next_step_index <= loop_input.step_budget:
            provider_response = loop_input.provider.next_action(
                AgentProviderStepInput(
                    problem_statement=loop_input.problem_statement,
                    verification_commands=loop_input.verification_commands,
                    step_index=next_step_index,
                    remaining_steps=loop_input.step_budget - next_step_index,
                    observations=observation_history,
                    context=loop_input.provider_context,
                )
            )
            if provider_response.status != "succeeded":
                handled = _provider_failure_handled(
                    provider_response=provider_response,
                    index=next_step_index,
                )
                record_handled_action(handled)
                status = "failed"
                summary = handled.step.observation.summary
                break
            if provider_response.tool_invocations:
                group_id = f"provider-{provider_turn_index}"
                for invocation in provider_response.tool_invocations:
                    if next_step_index > loop_input.step_budget:
                        status = "failed"
                        summary = "Agent loop exhausted step budget without final response"
                        break
                    grouped_invocation = invocation.model_copy(update={"group_id": group_id})
                    action = _invocation_to_tool_call_action(grouped_invocation)
                    observation = _execute_tool_invocation(
                        invocation=grouped_invocation,
                        repo_path=workspace_path,
                        settings=settings,
                        verification_commands=loop_input.verification_commands,
                    )
                    handled = _HandledAction(
                        stop=False,
                        status="failed",
                        summary="Agent loop ended without final response",
                        step=AgentStep(index=next_step_index, action=action, observation=observation),
                    )
                    record_handled_action(handled, tool_invocation=grouped_invocation)
                    next_step_index += 1
                provider_turn_index += 1
                if status == "failed" and summary == "Agent loop exhausted step budget without final response":
                    break
                continue
            if len(provider_response.actions) != 1:
                handled = _invalid_provider_actions_handled(
                    actions=provider_response.actions,
                    index=next_step_index,
                )
                record_handled_action(handled)
                status = "failed"
                summary = handled.step.observation.summary
                break
            handled = _handle_action_payload(
                payload=provider_response.actions[0],
                index=next_step_index,
                workspace_path=workspace_path,
                settings=settings,
                permission_mode=loop_input.permission_mode,
                verification_commands=loop_input.verification_commands,
            )
            record_handled_action(handled)
            next_step_index += 1
            provider_turn_index += 1
            if handled.stop:
                status, summary = apply_final_response_gate(handled)
                break
        else:
            status = "failed"
            summary = "Agent loop exhausted step budget without final response"
```

Change `record_handled_action()` signature:

```python
    def record_handled_action(
        handled: _HandledAction,
        tool_invocation: ToolInvocation | None = None,
    ) -> None:
```

and store:

```python
        observation_history.append(
            AgentObservationRecord(
                action=handled.step.action,
                tool_invocation=tool_invocation,
                observation=handled.step.observation,
            )
        )
```

- [ ] **Step 5: Adjust permission for native invocations**

Native invocation permission can reuse `_invocation_to_tool_call_action()` and existing `decide_permission()` for the first implementation. Before `_execute_tool_invocation()` in the native branch, evaluate:

```python
                    decision = decide_permission(action, loop_input.permission_mode)
                    if decision.status == "confirm":
                        confirmation = build_confirmation_request(action=action, decision=decision)
                        observation = Observation(
                            status="rejected",
                            summary="User confirmation required",
                            payload={"permission_decision": decision.model_dump(mode="json")},
                            error_message=decision.reason,
                        )
                        handled = _HandledAction(
                            stop=True,
                            status="needs_user_confirmation",
                            summary=observation.summary,
                            step=AgentStep(index=next_step_index, action=confirmation, observation=observation),
                        )
                        record_handled_action(handled, tool_invocation=grouped_invocation)
                        status = "needs_user_confirmation"
                        summary = observation.summary
                        break
                    if decision.status == "deny":
                        observation = Observation(
                            status="rejected",
                            summary="Tool denied by permission gate",
                            payload={"permission_decision": decision.model_dump(mode="json")},
                            error_message=decision.reason,
                        )
                    else:
                        observation = _execute_tool_invocation(
                            invocation=grouped_invocation,
                            repo_path=workspace_path,
                            settings=settings,
                            verification_commands=loop_input.verification_commands,
                        )
```

After the inner loop, if `status == "needs_user_confirmation"`, break out of the provider loop.

- [ ] **Step 6: Run loop tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_agent_loop.py tests/unit/test_permission_gate.py -q
PYTHONPATH=. python -m ruff check app/agent/loop.py tests/unit/test_agent_loop.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/agent/loop.py tests/unit/test_agent_loop.py tests/unit/test_permission_gate.py
git commit -m "feat: execute native tool invocations"
```

---

### Task 8: Align Permissions and Prompt Contract

**Files:**
- Modify: `app/agent/permission.py`
- Modify: `app/agent/prompt_context.py`
- Modify: `tests/unit/test_permission_gate.py`
- Modify: `tests/unit/test_prompt_context.py`

- [ ] **Step 1: Add permission and prompt tests**

Append to `tests/unit/test_permission_gate.py`:

```python
def test_guided_mode_allows_structured_apply_patch_in_worktree() -> None:
    decision = decide_permission(tool_call("apply_patch"), mode="guided")

    assert decision.status == "allow"
    assert decision.risk_level == "medium"
    assert "worktree patching" in decision.reason


def test_safe_mode_requires_confirmation_for_apply_patch() -> None:
    decision = decide_permission(tool_call("apply_patch"), mode="safe")

    assert decision.status == "confirm"
    assert decision.risk_level == "medium"
```

Append to `tests/unit/test_prompt_context.py`:

```python
def test_system_prompt_prefers_native_tools_over_json_actions() -> None:
    messages = build_provider_messages(
        AgentProviderStepInput(
            problem_statement="fix",
            verification_commands=[],
            step_index=1,
            remaining_steps=4,
            observations=[],
        )
    )

    assert "Use native tool calls when tools are available" in messages[0].content
    assert "Return JSON only when no native tool call is needed" in messages[0].content
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_permission_gate.py tests/unit/test_prompt_context.py -q
```

Expected: FAIL until prompt and permission wording are aligned.

- [ ] **Step 3: Update permission wording**

In `app/agent/permission.py`, change the guided patch branch:

```python
        if tool_name in {"apply_patch", "apply_patch_to_worktree"}:
            return PermissionDecision(
                status="allow",
                reason="guided mode allows worktree patching before user apply",
                risk_level=risk,
            )
```

Keep `_TOOL_RISK["apply_patch"] = "medium"`.

- [ ] **Step 4: Update system prompt**

In `app/agent/prompt_context.py`, edit `_system_prompt()` so its opening contract says:

```python
        "You are MendCode's action planner. Use native tool calls when tools are available. "
        "Return JSON only when no native tool call is needed, such as final_response or "
        "a patch_proposal fallback. The JSON object must be a valid MendCodeAction.\n"
```

Keep the existing repair workflow and final-response warning.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
PYTHONPATH=. python -m pytest tests/unit/test_permission_gate.py tests/unit/test_prompt_context.py tests/unit/test_openai_compatible_provider.py -q
PYTHONPATH=. python -m ruff check app/agent/permission.py app/agent/prompt_context.py
```

Expected: PASS.

Commit:

```bash
git add app/agent/permission.py app/agent/prompt_context.py tests/unit/test_permission_gate.py tests/unit/test_prompt_context.py
git commit -m "docs: align native tool prompt contract"
```

---

### Task 9: Final Verification and Roadmap Sync

**Files:**
- Modify: `MendCode_开发方案.md`
- Modify: `MendCode_全局路线图.md`
- Modify: `MendCode_TUI产品基调与交互方案.md`
- Test: full suite and lint

- [ ] **Step 1: Run full tests**

Run:

```bash
PYTHONPATH=. uv run --isolated --python 3.12 --with-requirements requirements.txt python -m pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run ruff**

Run:

```bash
PYTHONPATH=. uv run --isolated --python 3.12 --with-requirements requirements.txt python -m ruff check .
```

Expected: PASS.

- [ ] **Step 3: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Update root docs with implementation reality**

Update the three root docs only after the test and lint commands pass:

- `MendCode_开发方案.md`: mark native OpenAI tool-call registry support as implemented and note JSON Action remains fallback.
- `MendCode_全局路线图.md`: move ToolRegistry/native tool calling from planned to completed for this slice.
- `MendCode_TUI产品基调与交互方案.md`: note that the Agent can now call structured tools through OpenAI tool calls while preserving permission gates.

Use concise bullets and include the exact verification commands from Steps 1 and 2.

- [ ] **Step 5: Review diff**

Run:

```bash
git diff --stat
git diff -- app tools tests MendCode_开发方案.md MendCode_全局路线图.md MendCode_TUI产品基调与交互方案.md
```

Expected: diff only covers ToolRegistry, OpenAI provider native tool calls, loop integration, prompt/permission tests, and docs.

- [ ] **Step 6: Commit final docs and any verification fixes**

```bash
git add MendCode_开发方案.md MendCode_全局路线图.md MendCode_TUI产品基调与交互方案.md
git commit -m "docs: sync native tool calling progress"
```

- [ ] **Step 7: Final status**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: clean working tree and recent commits for the registry, provider, loop, prompt, and docs tasks.

---

## Self-Review Checklist

- Spec coverage:
  - ToolRegistry and ToolSpec are covered in Tasks 1 and 2.
  - Pydantic args models are covered in Task 2.
  - OpenAI `tools` schema generation is covered in Tasks 1, 2, and 5.
  - Native `tool_calls` parsing is covered in Task 5.
  - Tool results as `role="tool"` messages are covered in Task 6.
  - Sequential native invocation execution is covered in Task 7.
  - Permission behavior is covered in Tasks 3, 7, and 8.
  - JSON Action fallback is preserved in Tasks 4, 5, and 7.
  - Full verification and roadmap sync are covered in Task 9.

- Type consistency:
  - `ToolInvocation` is defined in `app/tools/structured.py` and referenced from provider, prompt context, and loop.
  - `ProviderResponse.tool_invocations` is a list of `ToolInvocation`.
  - `AgentObservationRecord.tool_invocation` carries native tool metadata for prompt reconstruction.
  - OpenAI transport models live in `app/agent/openai_compatible.py`; registry models stay provider-neutral.

- Scope:
  - This plan does not add non-OpenAI providers, streaming, long-running shell sessions, commit/push automation, or parallel tool execution.
