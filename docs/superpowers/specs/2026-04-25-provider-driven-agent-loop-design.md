# Provider-Driven Agent Loop Design

## Purpose

MendCode's current Agent loop executes a prebuilt list of actions. That is useful for testing the execution substrate, but it is not the dynamic tool-use loop described in the TUI product route.

This slice changes the loop shape so the loop asks a provider for the next `MendCodeAction` after each observation. It does not add a real LLM provider, TUI, workspace apply, commit, push, or discard flow.

## Product Fit

This work directly advances the current TUI Code Agent route:

```text
TUI input -> Agent Action Loop -> Permission Gate -> Tool Execution -> Observation
```

It keeps the project on the newest route by replacing fixed action playback with provider-driven iteration while preserving the existing safety and verification gates.

## Scope

In scope:

- Add a provider-step input model containing the problem statement, verification commands, current step index, remaining step budget, and prior observations.
- Add a provider method that returns one next action at a time.
- Keep `ScriptedAgentProvider` as the deterministic test and transitional provider.
- Update `run_agent_loop()` to support provider-driven execution.
- Keep the existing list-based action path only as compatibility/test support if that is the smallest safe transition.
- Ensure failed observations are included in provider history.
- Preserve permission gate behavior before every tool execution.
- Preserve final-response verification gating so a completed response cannot hide a failed last meaningful observation.
- Preserve JSONL trace events.
- Keep the current `mendcode fix "<problem>" --test "<command>"` behavior compatible.

Out of scope:

- OpenAI, Anthropic, or OpenAI-compatible adapters.
- Network calls.
- TUI rendering.
- User confirmation continuation after a confirmation request.
- Applying worktree changes back to the main workspace.
- Commit or push automation.
- Multi-agent orchestration.
- Retry strategy beyond the existing step budget.

## Architecture

The provider becomes a stepwise decision source. Instead of returning a complete action list for the whole run, the loop calls the provider once per step:

```text
AgentLoop
  -> provider.next_action(step_input)
  -> parse MendCodeAction
  -> permission gate
  -> execute tool or record action
  -> append observation to history
  -> repeat until final response, confirmation request, failure, or step budget
```

`ScriptedAgentProvider` will implement this interface by maintaining deterministic planning rules. It can still produce the same sequence as today for CLI compatibility:

1. `repo_status`
2. `detect_project`
3. each requested verification command
4. optional failure-location actions in a second loop, if invoked by the CLI
5. `final_response`

The loop should not know vendor-specific provider formats. It only receives dictionaries that must validate as `MendCodeAction`.

## Data Flow

Provider step input should contain:

- `problem_statement`
- `verification_commands`
- `step_index`
- `remaining_steps`
- `observations`
- optional `phase` or `context` string for scripted behavior such as initial verification versus failure location

Each observation history entry should include:

- the action that was attempted when available
- the resulting observation

This keeps the provider able to react to command failures, rejected tool calls, read results, search results, and patch outcomes.

## Error Handling

Provider failure should become a failed Agent loop result with a structured observation. Invalid provider output should use the existing invalid-action observation path.

Permission confirmation keeps the current behavior: the loop emits a `user_confirmation_request`, records a rejected observation, sets status to `needs_user_confirmation`, and stops. Continuing after user confirmation belongs to a separate TUI/session slice.

Step budget exhaustion should return a failed result with a clear summary such as `Agent loop exhausted step budget without final response`.

## CLI Compatibility

`mendcode fix` should still:

- require at least one `--test` command
- create an isolated worktree
- run repo status and project detection
- run supplied verification commands
- parse pytest-style failure insight
- run the existing failure-location context collection when possible
- print run id, status, summary, workspace path, trace path, failure insight, and location steps

The output format does not need to be redesigned in this slice.

## Testing

Tests should be written first.

Required coverage:

- Provider-driven loop executes a scripted `search_code` action and completes.
- Provider-driven loop passes failed tool observations into the next provider call.
- Provider-driven loop stops with `needs_user_confirmation` when permission gate requires confirmation.
- Provider-driven loop returns failed status when the step budget is exhausted before a final response.
- Invalid provider action becomes a rejected observation.
- Final response cannot report completed when the last meaningful observation failed.
- Existing CLI `fix` integration still reports failure insight and location context.

Regression coverage should keep current list-based action tests green until that compatibility path is intentionally removed.

## Documentation Updates

After implementation, update:

- `MendCode_开发方案.md`
- `MendCode_全局路线图.md`
- `MendCode_TUI产品基调与交互方案.md`

Only mark checkboxes complete when code and verification evidence exist.

## Acceptance Criteria

- `python -m pytest -q` passes.
- `ruff check .` passes.
- `mendcode fix` transitional behavior does not regress.
- `run_agent_loop()` can run by asking a provider for one action per step.
- Observation history is available to provider decisions.
- No real LLM or TUI code is introduced in this slice.
