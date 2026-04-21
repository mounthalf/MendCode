import json
from pathlib import Path

from app.orchestrator.runner import run_task_preview
from app.schemas.task import TaskSpec


def build_task() -> TaskSpec:
    return TaskSpec(
        task_id="demo-ci-001",
        task_type="ci_fix",
        title="Fix failing unit test",
        repo_path="/repo/demo",
        entry_artifacts={"failure_summary": "Unit test failure"},
        verification_commands=["python -c \"print('ok')\""],
    )


def test_run_task_preview_returns_completed_state(tmp_path):
    result = run_task_preview(build_task(), tmp_path)

    assert result.task_id == "demo-ci-001"
    assert result.task_type == "ci_fix"
    assert result.status == "completed"
    assert result.current_step == "summarize"
    assert result.verification is not None
    assert result.verification.status == "passed"
    assert result.summary == "Verification passed: 1/1 commands succeeded"


def test_run_task_preview_writes_started_and_completed_events(tmp_path):
    result = run_task_preview(build_task(), tmp_path)
    trace_file = Path(result.trace_path)

    assert trace_file.exists()
    lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines]

    assert result.trace_path == str(trace_file)
    assert all(event["run_id"] == result.run_id for event in events)
    assert [event["event_type"] for event in events] == [
        "run.started",
        "run.verification.started",
        "run.verification.command.completed",
        "run.completed",
    ]
    assert events[0]["payload"]["task_id"] == "demo-ci-001"
    assert events[1]["payload"]["status"] == "running"
    assert events[1]["payload"]["command_count"] == 1
    assert events[2]["payload"]["command"] == "python -c \"print('ok')\""
    assert events[3]["payload"]["status"] == "completed"


def test_run_task_preview_uses_trace_recorder_return_path(tmp_path, monkeypatch):
    custom_trace_path = tmp_path / "nested" / "preview-custom.jsonl"

    def fake_record(self, event):
        custom_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with custom_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json")))
            handle.write("\n")
        return custom_trace_path

    monkeypatch.setattr("app.orchestrator.runner.TraceRecorder.record", fake_record)

    result = run_task_preview(build_task(), tmp_path)

    assert result.trace_path == str(custom_trace_path)
    assert Path(result.trace_path).exists()


def test_run_task_preview_marks_run_passed_when_all_commands_succeed(tmp_path):
    task = TaskSpec(
        task_id="demo-ci-001",
        task_type="ci_fix",
        title="Verify success path",
        repo_path="/repo/demo",
        entry_artifacts={},
        verification_commands=["python -c \"print('ok')\""],
    )

    result = run_task_preview(task, tmp_path)

    assert result.status == "completed"
    assert result.current_step == "summarize"
    assert result.verification is not None
    assert result.verification.status == "passed"
    assert result.verification.passed_count == 1
    assert result.verification.failed_count == 0
    assert result.summary == "Verification passed: 1/1 commands succeeded"


def test_run_task_preview_marks_run_failed_when_a_command_fails(tmp_path):
    task = TaskSpec(
        task_id="demo-ci-001",
        task_type="ci_fix",
        title="Verify fail path",
        repo_path="/repo/demo",
        entry_artifacts={},
        verification_commands=[
            "python -c \"print('ok')\"",
            "python -c \"import sys; sys.exit(2)\"",
        ],
    )

    result = run_task_preview(task, tmp_path)

    assert result.status == "failed"
    assert result.verification is not None
    assert result.verification.status == "failed"
    assert result.verification.passed_count == 1
    assert result.verification.failed_count == 1
    assert "Verification failed" in result.summary


def test_run_task_preview_fails_when_no_verification_commands_are_defined(tmp_path):
    task = TaskSpec(
        task_id="demo-ci-001",
        task_type="ci_fix",
        title="No verification commands",
        repo_path="/repo/demo",
        entry_artifacts={},
        verification_commands=[],
    )

    result = run_task_preview(task, tmp_path)

    assert result.status == "failed"
    assert result.verification is not None
    assert result.verification.failed_count == 1
    assert result.summary == "Verification failed: no verification commands provided"
