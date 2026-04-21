# Phase 1 Run Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal `task run` execution skeleton that loads a task, creates a `RunState`, writes `run.started` and `run.completed` trace events, and prints a run summary without touching repositories or executing verification commands.

**Architecture:** Keep the new execution path deliberately narrow. Add a small `RunState` schema, a synchronous runner in `app/orchestrator/runner.py`, and wire it into the existing CLI. Reuse current task loading, settings, and trace recording code instead of adding new layers.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, orjson, pytest, rich

---

### Task 1: Add Minimal RunState Schema

**Files:**
- Create: `app/schemas/run_state.py`
- Modify: `app/schemas/__init__.py`
- Create: `tests/unit/test_run_state.py`
- Test: `tests/unit/test_run_state.py`

- [ ] **Step 1: Write the failing RunState tests**

`tests/unit/test_run_state.py`

```python
from app.schemas.run_state import RunState


def test_run_state_serializes_expected_fields():
    state = RunState(
        run_id="preview-123456789abc",
        task_id="demo-ci-001",
        task_type="ci_fix",
        status="completed",
        current_step="summarize",
        summary="Task preview completed",
        trace_path="/tmp/demo.jsonl",
    )

    payload = state.model_dump()

    assert payload == {
        "run_id": "preview-123456789abc",
        "task_id": "demo-ci-001",
        "task_type": "ci_fix",
        "status": "completed",
        "current_step": "summarize",
        "summary": "Task preview completed",
        "trace_path": "/tmp/demo.jsonl",
    }


def test_run_state_rejects_unknown_fields():
    try:
        RunState(
            run_id="preview-123456789abc",
            task_id="demo-ci-001",
            task_type="ci_fix",
            status="running",
            current_step="bootstrap",
            summary="Starting task run",
            trace_path="/tmp/demo.jsonl",
            extra_field="unexpected",
        )
    except Exception as exc:
        assert "extra_field" in str(exc)
    else:
        raise AssertionError("RunState should reject unknown fields")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_run_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.run_state'`

- [ ] **Step 3: Write the minimal RunState schema**

`app/schemas/run_state.py`

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    task_type: Literal["ci_fix", "test_regression_fix", "pr_review"]
    status: Literal["running", "completed", "failed"]
    current_step: Literal["bootstrap", "summarize"]
    summary: str
    trace_path: str
```

`app/schemas/__init__.py`

```python
"""Schema package exports."""

from app.schemas.run_state import RunState
from app.schemas.task import TaskSpec
from app.schemas.trace import TraceEvent

__all__ = ["RunState", "TaskSpec", "TraceEvent"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_run_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/__init__.py app/schemas/run_state.py tests/unit/test_run_state.py
git commit -m "feat: add minimal run state schema"
```

### Task 2: Add Synchronous Runner And Trace Tests

**Files:**
- Create: `app/orchestrator/__init__.py`
- Create: `app/orchestrator/runner.py`
- Create: `tests/unit/test_runner.py`
- Test: `tests/unit/test_runner.py`

- [ ] **Step 1: Write the failing runner tests**

`tests/unit/test_runner.py`

```python
import json

from app.orchestrator.runner import run_task_preview
from app.schemas.task import TaskSpec


def build_task() -> TaskSpec:
    return TaskSpec(
        task_id="demo-ci-001",
        task_type="ci_fix",
        title="Fix failing unit test",
        repo_path="/repo/demo",
        entry_artifacts={"failure_summary": "Unit test failure"},
        verification_commands=["pytest -q"],
    )


def test_run_task_preview_returns_completed_state(tmp_path):
    result = run_task_preview(build_task(), tmp_path)

    assert result.task_id == "demo-ci-001"
    assert result.task_type == "ci_fix"
    assert result.status == "completed"
    assert result.current_step == "summarize"
    assert result.summary == "Task preview completed"


def test_run_task_preview_writes_started_and_completed_events(tmp_path):
    result = run_task_preview(build_task(), tmp_path)
    trace_file = tmp_path / f"{result.run_id}.jsonl"

    lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines]

    assert trace_file.exists()
    assert result.trace_path == str(trace_file)
    assert [event["event_type"] for event in events] == [
        "run.started",
        "run.completed",
    ]
    assert events[0]["payload"]["task_id"] == "demo-ci-001"
    assert events[1]["payload"]["status"] == "completed"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.orchestrator'`

- [ ] **Step 3: Write the minimal runner**

`app/orchestrator/__init__.py`

```python
"""Orchestrator package."""
```

`app/orchestrator/runner.py`

```python
from pathlib import Path
from uuid import uuid4

from app.schemas.run_state import RunState
from app.schemas.task import TaskSpec
from app.schemas.trace import TraceEvent
from app.tracing.recorder import TraceRecorder


def run_task_preview(task: TaskSpec, traces_dir: Path) -> RunState:
    recorder = TraceRecorder(traces_dir)
    run_id = f"preview-{uuid4().hex[:12]}"
    trace_path = traces_dir / f"{run_id}.jsonl"

    recorder.record(
        TraceEvent(
            run_id=run_id,
            event_type="run.started",
            message="Started task preview run",
            payload={
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "running",
                "summary": "Task preview started",
            },
        )
    )

    recorder.record(
        TraceEvent(
            run_id=run_id,
            event_type="run.completed",
            message="Completed task preview run",
            payload={
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "completed",
                "summary": "Task preview completed",
            },
        )
    )

    return RunState(
        run_id=run_id,
        task_id=task.task_id,
        task_type=task.task_type,
        status="completed",
        current_step="summarize",
        summary="Task preview completed",
        trace_path=str(trace_path),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/orchestrator/__init__.py app/orchestrator/runner.py tests/unit/test_runner.py
git commit -m "feat: add task preview runner"
```

### Task 3: Wire Runner Into CLI

**Files:**
- Modify: `app/cli/main.py`
- Modify: `tests/integration/test_cli.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write the failing CLI test**

Add this test to `tests/integration/test_cli.py`:

```python
def test_task_run_writes_trace_and_prints_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "run", str(task_file)])

    trace_files = sorted((tmp_path / "data" / "traces").glob("preview-*.jsonl"))

    assert result.exit_code == 0
    assert "Task Run" in result.stdout
    assert "demo-ci-001" in result.stdout
    assert "completed" in result.stdout
    assert len(trace_files) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/integration/test_cli.py::test_task_run_writes_trace_and_prints_summary -v`
Expected: FAIL with `No such command 'run'`

- [ ] **Step 3: Add the `task run` command**

Update `app/cli/main.py` to import and use the runner:

```python
from app.orchestrator.runner import run_task_preview
```

Add this command below `show_task`:

```python
@task_app.command("run")
def run_task(file_path: Path) -> None:
    task = _load_task_spec_or_exit(file_path)
    settings = get_settings()
    ensure_data_directories(settings)

    try:
        state = run_task_preview(task, settings.traces_dir)
    except OSError as exc:
        typer.echo(f"Task run failed while writing trace output: {exc}")
        raise typer.Exit(code=1)

    table = Table(title="Task Run")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", state.run_id)
    table.add_row("task_id", state.task_id)
    table.add_row("task_type", state.task_type)
    table.add_row("status", state.status)
    table.add_row("current_step", state.current_step)
    table.add_row("summary", state.summary)
    table.add_row("trace_path", state.trace_path)
    console.print(table)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/integration/test_cli.py::test_task_run_writes_trace_and_prints_summary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/cli/main.py tests/integration/test_cli.py
git commit -m "feat: add task run cli command"
```

### Task 4: Verify Full Phase 1A Slice

**Files:**
- Modify: `README.md`
- Test: `tests/unit/test_run_state.py`
- Test: `tests/unit/test_runner.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Add the new CLI command to README**

Update the CLI section in `README.md` to include:

```bash
mendcode task run data/tasks/demo.json
```

- [ ] **Step 2: Run the full targeted test set**

Run: `pytest tests/unit/test_run_state.py tests/unit/test_runner.py tests/integration/test_cli.py -v`
Expected: PASS

- [ ] **Step 3: Run the full project verification**

Run: `pytest -q`
Expected: PASS with all tests passing

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: Run the CLI smoke check**

Run: `python -m app.cli.main task run data/tasks/demo.json`
Expected: output includes `Task Run`, `run_id`, `demo-ci-001`, `completed`, and `trace_path`

- [ ] **Step 5: Commit**

```bash
git add README.md tests/unit/test_run_state.py tests/unit/test_runner.py tests/integration/test_cli.py app/schemas/run_state.py app/schemas/__init__.py app/orchestrator/__init__.py app/orchestrator/runner.py app/cli/main.py
git commit -m "feat: add phase 1 run skeleton"
```
