import json
import shlex
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()
PYTHON = shlex.quote(sys.executable)


def init_git_repo(path: Path) -> Path:
    repo_path = path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_path


def write_task_file(path: Path) -> Path:
    repo_path = init_git_repo(path)
    (repo_path / "target.txt").write_text("wrong\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "target.txt"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add target"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )

    task_file = path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "demo-ci-001",
                "task_type": "ci_fix",
                "title": "Fixed-flow demo repair",
                "repo_path": str(repo_path),
                "entry_artifacts": {
                    "search_query": "wrong",
                    "target_path_glob": "*.txt",
                    "old_text": "wrong",
                    "new_text": "fixed",
                },
                "verification_commands": [
                    f"{PYTHON} -c "
                    "\"from pathlib import Path; import sys; "
                    "sys.exit(0 if Path('target.txt').read_text(encoding='utf-8') == "
                    "'fixed\\n' else 1)\""
                ],
                "allowed_tools": ["read_file", "search_code", "apply_patch"],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    return task_file


def write_failing_task_file(path: Path) -> Path:
    repo_path = init_git_repo(path)
    task_file = path / "task-fail.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "demo-ci-002",
                "task_type": "ci_fix",
                "title": "Fail verification",
                "repo_path": str(repo_path),
                "entry_artifacts": {},
                "verification_commands": [f"{PYTHON} -c \"import sys; sys.exit(3)\""],
                "allowed_tools": ["read_file"],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    return task_file


def test_health_command_reports_status(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "MendCode" in result.stdout
    assert "status" in result.stdout
    assert "traces" in result.stdout


def test_task_validate_command_accepts_valid_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "validate", str(task_file)])

    assert result.exit_code == 0
    assert "Task file is valid" in result.stdout
    assert "demo-ci-001" in result.stdout


def test_task_validate_missing_file_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    missing_file = tmp_path / "missing.json"

    result = runner.invoke(app, ["task", "validate", str(missing_file)])

    assert result.exit_code != 0
    assert f"Task file not found: {missing_file}" in result.stdout


def test_task_validate_directory_returns_read_error(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))

    result = runner.invoke(app, ["task", "validate", str(tmp_path)])

    assert result.exit_code != 0
    assert "Task file could not be read" in result.stdout


def test_task_show_writes_trace_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "show", str(task_file)])

    trace_dir = tmp_path / "data" / "traces"
    trace_files = list(trace_dir.glob("*.jsonl"))

    assert result.exit_code == 0
    assert "Fixed-flow demo repair" in result.stdout
    assert len(trace_files) == 1

    trace_payload = json.loads(trace_files[0].read_text(encoding="utf-8").strip())
    assert trace_payload["event_type"] == "task.show"
    assert trace_payload["payload"]["task_id"] == "demo-ci-001"
    assert trace_payload["payload"]["title"] == "Fixed-flow demo repair"


def test_task_run_writes_trace_and_prints_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "run", str(task_file)], terminal_width=200)

    trace_files = sorted((tmp_path / "data" / "traces").glob("preview-*.jsonl"))

    assert result.exit_code == 0
    assert "Task Run" in result.stdout
    assert "demo-ci-001" in result.stdout
    assert "summarize" in result.stdout
    assert "completed" in result.stdout
    assert "passed_count" in result.stdout
    assert "failed_count" in result.stdout
    assert "selected_files" in result.stdout
    assert "applied_patch" in result.stdout
    assert "workspace_path" in result.stdout
    assert "target.txt" in result.stdout
    assert "yes" in result.stdout
    assert len(trace_files) == 1

    trace_path = str(trace_files[0])
    assert trace_path in result.stdout

    trace_lines = trace_files[0].read_text(encoding="utf-8").strip().splitlines()
    trace_events = [json.loads(line) for line in trace_lines]

    assert "run.workspace.cleanup" in [event["event_type"] for event in trace_events]
    assert trace_events[0]["payload"]["task_id"] == "demo-ci-001"
    assert trace_events[0]["payload"]["task_type"] == "ci_fix"
    assert trace_events[0]["payload"]["summary"] == "Task preview started"
    assert trace_events[0]["payload"]["workspace_path"].startswith(
        str(tmp_path / ".worktrees" / "preview-")
    )
    assert trace_events[1]["event_type"] == "run.tool.started"
    assert trace_events[1]["payload"]["tool_name"] == "search_code"
    assert trace_events[2]["event_type"] == "run.tool.completed"
    assert trace_events[2]["payload"]["tool_name"] == "search_code"
    assert trace_events[7]["payload"]["command_count"] == 1
    assert trace_events[8]["payload"]["status"] == "passed"
    assert trace_events[-1]["payload"]["status"] == "completed"
    assert trace_events[-1]["payload"]["task_type"] == "ci_fix"
    assert trace_events[-1]["payload"]["summary"] == "Verification passed: 1/1 commands succeeded"


def test_task_run_prints_fixed_flow_state(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "run", str(task_file)], terminal_width=200)

    assert result.exit_code == 0
    assert "selected_files" in result.stdout
    assert "applied_patch" in result.stdout
    assert "target.txt" in result.stdout
    assert "yes" in result.stdout


def test_task_run_reports_passed_verification(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    task_file = write_task_file(tmp_path)

    result = runner.invoke(app, ["task", "run", str(task_file)], terminal_width=200)

    assert result.exit_code == 0
    assert "passed_count" in result.stdout
    assert "failed_count" in result.stdout
    assert "1" in result.stdout
    assert "Verification passed: 1/1 commands succeeded" in result.stdout


def test_task_run_reports_failed_verification_without_cli_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    task_file = write_failing_task_file(tmp_path)

    result = runner.invoke(app, ["task", "run", str(task_file)], terminal_width=200)

    assert result.exit_code == 0
    assert "failed" in result.stdout
    assert "passed_count" in result.stdout
    assert "failed_count" in result.stdout
    assert "First non-passed command: failed" in result.stdout
    assert f'{PYTHON} -c "import sys; sys.exit(3)"' in result.stdout


def test_fix_command_runs_verification_and_reports_failure_insight(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    repo_path = init_git_repo(tmp_path)
    command = (
        f"{PYTHON} -c "
        "\"print('FAILED tests/test_calculator.py::test_add - "
        "AssertionError: assert -1 == 5'); raise SystemExit(1)\""
    )

    result = runner.invoke(
        app,
        [
            "fix",
            "修复 pytest 失败",
            "--test",
            command,
            "--repo",
            str(repo_path),
        ],
        terminal_width=200,
    )

    assert result.exit_code == 0
    assert "Agent Fix" in result.stdout
    assert "修复 pytest 失败" in result.stdout
    assert "run_id" in result.stdout
    assert "preview-" in result.stdout
    assert "status" in result.stdout
    assert "failed" in result.stdout
    assert "failed_node" in result.stdout
    assert "tests/test_calculator.py::test_add" in result.stdout
    assert "error_summary" in result.stdout
    assert "AssertionError: assert -1 == 5" in result.stdout
    assert "trace_path" in result.stdout
