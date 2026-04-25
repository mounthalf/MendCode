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


def test_agent_loop_executes_allowed_search_code_action(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

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


def test_agent_loop_turns_invalid_action_into_rejected_observation(tmp_path: Path) -> None:
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="bad action",
            actions=[
                {
                    "type": "tool_call",
                    "action": "delete_repo",
                    "reason": "bad",
                    "args": {},
                }
            ],
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.steps[0].observation.status == "rejected"
    assert result.steps[0].observation.summary == "Invalid MendCode action"


def test_agent_loop_returns_confirmation_request_when_permission_requires_it(
    tmp_path: Path,
) -> None:
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


def test_agent_loop_does_not_complete_after_failed_tool_observation(tmp_path: Path) -> None:
    result = run_agent_loop(
        AgentLoopInput(
            repo_path=tmp_path,
            problem_statement="failed verification",
            actions=[
                {
                    "type": "tool_call",
                    "action": "run_command",
                    "reason": "run failing command",
                    "args": {"command": "python -c 'raise SystemExit(1)'"},
                },
                {
                    "type": "final_response",
                    "status": "completed",
                    "summary": "done",
                },
            ],
        ),
        settings_for(tmp_path),
    )

    assert result.status == "failed"
    assert result.summary == "Agent loop ended with failed observations"
