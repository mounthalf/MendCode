# TUI Agent Route Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old fixed-flow task/eval/API route with a minimal Agent Action Loop aligned to the TUI Code Agent product direction.

**Architecture:** Keep the existing safety foundations: permission gate, read-only tools, worktree execution, verification executor, and trace recorder. Remove old task JSON, batch eval, FastAPI, and fixed-flow orchestration as product paths. Introduce `app.agent.loop` as the new runner boundary that turns MendCode actions into permission decisions, tool execution, observations, trace events, and final run state.

**Tech Stack:** Python 3.11, Pydantic v2, Typer, Rich, pytest, existing workspace/tool/tracing modules.

---

### Task 1: Add Agent Loop Tests

**Files:**
- Create: `tests/unit/test_agent_loop.py`

- [ ] **Step 1: Write failing tests for the new loop**

```python
from pathlib import Path

from app.agent.loop import AgentLoopInput, run_agent_loop
from app.config.settings import Settings


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


def test_agent_loop_executes_allowed_search_code_action(tmp_path: Path):
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="find add",
            actions=[
                {
                    "type": "tool_call",
                    "action": "search_code",
                    "reason": "locate implementation",
                    "args": {"query": "def add", "glob": "*.py"},
                },
                {"type": "final_response", "status": "completed", "summary": "done"},
            ],
        ),
        settings_for(tmp_path),
    )

    assert result.status == "completed"
    assert result.steps[0].observation.status == "succeeded"
    assert result.steps[0].observation.payload["total_matches"] == 1
    assert result.trace_path is not None


def test_agent_loop_turns_invalid_action_into_rejected_observation(tmp_path: Path):
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="bad action",
            actions=[{"type": "tool_call", "action": "delete_repo", "reason": "bad", "args": {}}],
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.steps[0].observation.status == "rejected"
    assert result.steps[0].observation.summary == "Invalid MendCode action"


def test_agent_loop_returns_confirmation_request_when_permission_requires_it(tmp_path: Path):
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="safe mode command",
            permission_mode="safe",
            actions=[
                {
                    "type": "tool_call",
                    "action": "run_command",
                    "reason": "run tests",
                    "args": {"command": "pytest -q"},
                }
            ],
        ),
        settings_for(tmp_path),
    )

    assert result.status == "needs_user_confirmation"
    assert result.steps[0].action.type == "user_confirmation_request"
    assert result.steps[0].observation.status == "rejected"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/unit/test_agent_loop.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.loop'`.

### Task 2: Implement Minimal Agent Loop

**Files:**
- Create: `app/agent/loop.py`
- Modify: `app/schemas/__init__.py`

- [ ] **Step 1: Implement `AgentLoopInput`, `AgentLoopResult`, `AgentStep`, and `run_agent_loop`**
- [ ] **Step 2: Convert `ToolResult` into `Observation`**
- [ ] **Step 3: Run `python -m pytest tests/unit/test_agent_loop.py -q` and verify pass**

### Task 3: Remove Old Route

**Files:**
- Delete: `app/api/server.py`
- Delete: `app/api/__init__.py`
- Delete: `app/eval/batch.py`
- Delete: `app/eval/__init__.py`
- Delete: `app/orchestrator/fixed_flow.py`
- Delete: `app/orchestrator/runner.py`
- Delete: `app/schemas/eval.py`
- Delete: `app/schemas/task.py`
- Delete: `app/schemas/run_state.py`
- Delete old fixed-flow/eval/API tests.

- [ ] **Step 1: Remove deleted modules from imports and CLI**
- [ ] **Step 2: Remove FastAPI and uvicorn dependencies**
- [ ] **Step 3: Run affected tests and fix import fallout**

### Task 4: CLI Route Alignment

**Files:**
- Modify: `app/cli/main.py`
- Modify: `README.md`

- [ ] **Step 1: Keep `version`, `health`, and transitional `fix`**
- [ ] **Step 2: Make `fix` call `run_agent_loop` with a minimal verification command action**
- [ ] **Step 3: Remove `task` and `eval` commands**
- [ ] **Step 4: Update README so `mendcode` direction is primary**

### Task 5: Verification

**Files:**
- Modify tests as needed.

- [ ] **Step 1: Run `python -m pytest -q`**
- [ ] **Step 2: Run `python -m ruff check .`**
- [ ] **Step 3: Confirm no imports reference deleted modules**

Run: `rg "TaskSpec|RunState|fixed_flow|run_task_preview|BatchEval|FastAPI|task run|old_text" app tests README.md`
Expected: no app/test references except product docs explaining deprecated behavior.
