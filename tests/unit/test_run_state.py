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
