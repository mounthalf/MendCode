# Provider-Driven Agent Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change MendCode's Agent loop from fixed action playback to provider-driven step-by-step action selection while preserving the current CLI `fix` behavior.

**Architecture:** Introduce provider step input/history models and a `next_action()` provider method. Add a provider-driven path to `run_agent_loop()` that asks the provider for one action per step, records each observation, and stops on final response, confirmation, provider failure, invalid action, or step budget exhaustion. Keep the existing list-based action path for regression compatibility during this transition.

**Tech Stack:** Python 3.11, Pydantic v2, Typer, Rich, pytest, ruff.

---

## File Structure

- Modify `app/agent/provider.py`
  - Add `AgentObservationRecord`.
  - Add `AgentProviderStepInput`.
  - Add `AgentProvider`.
  - Add `ScriptedAgentProvider.next_action()`.
  - Keep `plan_actions()` and `plan_failure_location_actions()` as compatibility helpers.

- Modify `app/agent/loop.py`
  - Add optional `provider`, `verification_commands`, and `provider_context` fields to `AgentLoopInput`.
  - Add provider-driven execution path.
  - Preserve existing list-based execution behavior for compatibility.
  - Convert provider failure into a failed observation and failed loop result.
  - Return a clear failed result on step budget exhaustion.

- Modify `app/cli/main.py`
  - Call `run_agent_loop()` with `provider=ScriptedAgentProvider()` and `verification_commands=test_commands`.
  - Keep the failure-location loop behavior compatible, using provider-driven mode for the second loop as well.

- Modify `tests/unit/test_agent_provider.py`
  - Add tests for stepwise scripted provider behavior.

- Modify `tests/unit/test_agent_loop.py`
  - Add provider-driven loop tests from the spec.
  - Keep existing list-based loop tests green.

- Modify `tests/integration/test_cli.py`
  - Keep current CLI behavior test passing; only adjust if output changes unintentionally.

- Modify documentation after code verification:
  - `MendCode_开发方案.md`
  - `MendCode_全局路线图.md`
  - `MendCode_TUI产品基调与交互方案.md`

---

### Task 1: Provider Step Models And Scripted Provider

**Files:**
- Modify: `app/agent/provider.py`
- Test: `tests/unit/test_agent_provider.py`

- [ ] **Step 1: Write failing tests for provider step behavior**

Add these tests to `tests/unit/test_agent_provider.py`:

```python
from app.agent.provider import (
    AgentProviderStepInput,
    AgentObservationRecord,
    ScriptedAgentProvider,
)
from app.schemas.agent_action import Observation, ToolCallAction


def test_scripted_provider_returns_initial_actions_one_step_at_a_time() -> None:
    provider = ScriptedAgentProvider()

    first = provider.next_action(
        AgentProviderStepInput(
            problem_statement="fix tests",
            verification_commands=["python -m pytest -q"],
            step_index=1,
            remaining_steps=4,
            observations=[],
        )
    )
    second = provider.next_action(
        AgentProviderStepInput(
            problem_statement="fix tests",
            verification_commands=["python -m pytest -q"],
            step_index=2,
            remaining_steps=3,
            observations=[],
        )
    )
    third = provider.next_action(
        AgentProviderStepInput(
            problem_statement="fix tests",
            verification_commands=["python -m pytest -q"],
            step_index=3,
            remaining_steps=2,
            observations=[],
        )
    )

    assert first.status == "succeeded"
    assert first.action is not None
    assert first.action["type"] == "tool_call"
    assert first.action["action"] == "repo_status"
    assert second.action is not None
    assert second.action["action"] == "detect_project"
    assert third.action is not None
    assert third.action["action"] == "run_command"
    assert third.action["args"] == {"command": "python -m pytest -q"}
```

Add this test for provider history and final response:

```python
def test_scripted_provider_returns_final_response_after_scripted_steps() -> None:
    provider = ScriptedAgentProvider()

    response = provider.next_action(
        AgentProviderStepInput(
            problem_statement="fix tests",
            verification_commands=["python -m pytest -q"],
            step_index=4,
            remaining_steps=1,
            observations=[
                AgentObservationRecord(
                    action=ToolCallAction(
                        type="tool_call",
                        action="run_command",
                        reason="run verification",
                        args={"command": "python -m pytest -q"},
                    ),
                    observation=Observation(
                        status="failed",
                        summary="Ran command: python -m pytest -q",
                        payload={"status": "failed"},
                        error_message="tests failed",
                    ),
                )
            ],
        )
    )

    assert response.status == "succeeded"
    assert response.action is not None
    assert response.action["type"] == "final_response"
    assert response.action["status"] == "completed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_agent_provider.py -q
```

Expected: FAIL because `AgentProviderStepInput`, `AgentObservationRecord`, and `next_action()` do not exist.

- [ ] **Step 3: Implement provider models and `next_action()`**

Update `app/agent/provider.py` with these additions while keeping existing behavior:

```python
from typing import Protocol

from app.schemas.agent_action import MendCodeAction


class AgentObservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MendCodeAction | None = None
    observation: Observation


class AgentProviderStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_statement: str
    verification_commands: list[str]
    step_index: int = Field(ge=1)
    remaining_steps: int = Field(ge=0)
    observations: list[AgentObservationRecord] = Field(default_factory=list)
    context: str | None = None


class AgentProvider(Protocol):
    def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
        ...
```

Add `ScriptedAgentProvider.next_action()` by deriving the action sequence from `plan_actions()`:

```python
def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
    plan_response = self.plan_actions(
        AgentProviderInput(
            problem_statement=step_input.problem_statement,
            verification_commands=step_input.verification_commands,
        )
    )
    if plan_response.status != "succeeded":
        return plan_response

    action_index = step_input.step_index - 1
    if action_index >= len(plan_response.actions):
        return ProviderResponse(
            status="succeeded",
            actions=[
                {
                    "type": "final_response",
                    "status": "completed",
                    "summary": "Agent loop completed requested verification commands",
                }
            ],
        )

    return ProviderResponse(status="succeeded", actions=[plan_response.actions[action_index]])
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
python -m pytest tests/unit/test_agent_provider.py -q
```

Expected: PASS.

---

### Task 2: Provider-Driven Agent Loop Core

**Files:**
- Modify: `app/agent/loop.py`
- Test: `tests/unit/test_agent_loop.py`

- [ ] **Step 1: Write failing tests for provider-driven loop**

Add a test provider and these tests to `tests/unit/test_agent_loop.py`:

```python
from app.agent.provider import AgentProviderStepInput, ProviderResponse


class RecordingProvider:
    def __init__(self, actions: list[dict[str, object]]) -> None:
        self.actions = actions
        self.calls: list[AgentProviderStepInput] = []

    def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
        self.calls.append(step_input)
        index = len(self.calls) - 1
        if index >= len(self.actions):
            return ProviderResponse(
                status="succeeded",
                actions=[
                    {
                        "type": "final_response",
                        "status": "completed",
                        "summary": "done",
                    }
                ],
            )
        return ProviderResponse(status="succeeded", actions=[self.actions[index]])
```

Add:

```python
def test_agent_loop_asks_provider_for_each_next_action(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    provider = RecordingProvider(
        [
            {
                "type": "tool_call",
                "action": "search_code",
                "reason": "locate implementation",
                "args": {"query": "def add", "glob": "*.py"},
            },
            {"type": "final_response", "status": "completed", "summary": "done"},
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="find add",
            provider=provider,
            verification_commands=[],
            step_budget=4,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "completed"
    assert result.steps[0].observation.status == "succeeded"
    assert len(provider.calls) == 2
    assert provider.calls[0].step_index == 1
    assert provider.calls[1].step_index == 2
    assert provider.calls[1].observations[0].observation.status == "succeeded"
```

Add:

```python
def test_agent_loop_passes_failed_observation_to_provider(tmp_path: Path) -> None:
    provider = RecordingProvider(
        [
            {
                "type": "tool_call",
                "action": "run_command",
                "reason": "run failing command",
                "args": {"command": "python -c 'raise SystemExit(1)'"},
            },
            {"type": "final_response", "status": "failed", "summary": "failed"},
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="failed verification",
            provider=provider,
            verification_commands=["python -c 'raise SystemExit(1)'"],
            step_budget=4,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert len(provider.calls) == 2
    assert provider.calls[1].observations[0].observation.status == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_agent_loop.py -q
```

Expected: FAIL because `AgentLoopInput` does not accept `provider` or `verification_commands`.

- [ ] **Step 3: Implement provider-driven loop path**

Update `app/agent/loop.py`:

- Import provider types:

```python
from app.agent.provider import AgentObservationRecord, AgentProvider, AgentProviderStepInput
```

- Extend `AgentLoopInput`:

```python
actions: list[dict[str, object]] = Field(default_factory=list)
provider: AgentProvider | None = None
verification_commands: list[str] = Field(default_factory=list)
provider_context: str | None = None
```

Set `model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)` for `AgentLoopInput`.

- Add a provider execution branch to `run_agent_loop()`:

```python
if loop_input.provider is not None:
    payloads: list[dict[str, object]] = []
else:
    payloads = loop_input.actions[: loop_input.step_budget]
```

For provider mode, loop over `range(1, loop_input.step_budget + 1)`, call `next_action()`, validate that it returned exactly one action, and execute that action through the same action handling code used by the list path.

Use `AgentObservationRecord(action=action, observation=observation)` to build provider history after every step.

- [ ] **Step 4: Run loop tests**

Run:

```bash
python -m pytest tests/unit/test_agent_loop.py -q
```

Expected: PASS.

---

### Task 3: Provider Failure, Invalid Action, Confirmation, And Budget

**Files:**
- Modify: `app/agent/loop.py`
- Test: `tests/unit/test_agent_loop.py`

- [ ] **Step 1: Add failing edge-case tests**

Add:

```python
class FailingProvider:
    def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
        return ProviderResponse.failed("provider unavailable")


def test_agent_loop_turns_provider_failure_into_failed_result(tmp_path: Path) -> None:
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="provider failure",
            provider=FailingProvider(),
            step_budget=3,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.steps[0].observation.status == "failed"
    assert result.steps[0].observation.error_message == "provider unavailable"
```

Add:

```python
def test_agent_loop_rejects_invalid_provider_action(tmp_path: Path) -> None:
    provider = RecordingProvider([{"type": "tool_call", "action": "delete_repo"}])

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="bad provider action",
            provider=provider,
            step_budget=3,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.steps[0].observation.status == "rejected"
    assert result.steps[0].observation.summary == "Invalid MendCode action"
```

Add:

```python
def test_provider_driven_loop_stops_for_confirmation_request(tmp_path: Path) -> None:
    provider = RecordingProvider(
        [
            {
                "type": "tool_call",
                "action": "run_command",
                "reason": "run tests",
                "args": {"command": "pytest -q"},
            }
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="safe mode command",
            provider=provider,
            permission_mode="safe",
            verification_commands=["pytest -q"],
            step_budget=3,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "needs_user_confirmation"
    assert result.steps[0].action.type == "user_confirmation_request"
```

Add:

```python
def test_provider_driven_loop_fails_when_step_budget_exhausted(tmp_path: Path) -> None:
    provider = RecordingProvider(
        [
            {
                "type": "tool_call",
                "action": "search_code",
                "reason": "search forever",
                "args": {"query": "missing"},
            }
        ]
    )

    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="no final response",
            provider=provider,
            step_budget=1,
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.summary == "Agent loop exhausted step budget without final response"
```

- [ ] **Step 2: Run edge-case tests to verify they fail**

Run:

```bash
python -m pytest tests/unit/test_agent_loop.py -q
```

Expected: FAIL for at least provider failure and budget behavior.

- [ ] **Step 3: Implement edge-case behavior**

In provider-driven mode:

- If provider response is failed, append an `AgentStep` with a failed final response action and the provider observation, then stop with failed status.
- If provider returns no actions or more than one action for a single step, create a rejected invalid-action observation.
- If all provider steps are consumed without a final response, set:

```python
status = "failed"
summary = "Agent loop exhausted step budget without final response"
```

Keep the existing final-response verification gate unchanged.

- [ ] **Step 4: Run loop tests**

Run:

```bash
python -m pytest tests/unit/test_agent_loop.py -q
```

Expected: PASS.

---

### Task 4: CLI Uses Provider-Driven Mode

**Files:**
- Modify: `app/cli/main.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Update CLI integration expectation only if needed**

Run the existing CLI tests first:

```bash
python -m pytest tests/integration/test_cli.py -q
```

Expected before implementation: PASS.

- [ ] **Step 2: Route `fix` through provider-driven loop**

Update the main loop input in `app/cli/main.py`:

```python
loop_input = AgentLoopInput(
    repo_path=repo.resolve(),
    problem_statement=problem_statement,
    provider=provider,
    verification_commands=test_commands,
    step_budget=max_attempts + 3,
    use_worktree=True,
)
```

For failure-location context, either keep the existing action-list path or use a second deterministic provider-driven mode. If keeping action-list path is smaller and tests remain clear, leave it unchanged in this slice.

- [ ] **Step 3: Run CLI tests**

Run:

```bash
python -m pytest tests/integration/test_cli.py -q
```

Expected: PASS.

---

### Task 5: Documentation And Full Verification

**Files:**
- Modify: `MendCode_开发方案.md`
- Modify: `MendCode_全局路线图.md`
- Modify: `MendCode_TUI产品基调与交互方案.md`

- [ ] **Step 1: Update docs to mark provider-driven loop progress**

Update only items that now have code and verification evidence:

- Mark dynamic provider-driven loop foundation as complete where the docs currently describe the dynamic tool-use loop gap.
- Keep real LLM provider, TUI, user confirmation continuation, and apply/discard unchecked.
- Note that `ScriptedAgentProvider` now drives actions step by step but remains deterministic.

- [ ] **Step 2: Run focused tests**

Run:

```bash
python -m pytest tests/unit/test_agent_provider.py tests/unit/test_agent_loop.py tests/integration/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full tests and lint**

Run:

```bash
python -m pytest -q
ruff check .
```

Expected: both pass.

- [ ] **Step 4: Review git diff**

Run:

```bash
git diff --stat
git diff -- app/agent/provider.py app/agent/loop.py app/cli/main.py
```

Expected: changes are limited to provider-driven loop, CLI routing, tests, and route docs.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/agent/provider.py app/agent/loop.py app/cli/main.py tests/unit/test_agent_provider.py tests/unit/test_agent_loop.py tests/integration/test_cli.py MendCode_开发方案.md MendCode_全局路线图.md MendCode_TUI产品基调与交互方案.md docs/superpowers/plans/2026-04-25-provider-driven-agent-loop.md
git commit -m "feat: drive agent loop from provider steps"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: The plan covers provider-step input, one-action provider calls, observation history, provider failure, invalid action, confirmation stop, budget exhaustion, CLI compatibility, docs, tests, and lint.
- Scope control: The plan does not introduce real LLM providers, TUI rendering, workspace apply, commit/push automation, or user confirmation continuation.
- Type consistency: Provider step input, provider response, observation record, and loop input names are consistent across tasks.
