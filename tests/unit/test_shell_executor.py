import shlex
import sys
from pathlib import Path

from app.workspace.shell_executor import execute_shell_command
from app.workspace.shell_policy import ShellPolicy

PYTHON = shlex.quote(sys.executable)


def make_policy(root: Path, timeout_seconds: int = 10) -> ShellPolicy:
    return ShellPolicy(allowed_root=root, timeout_seconds=timeout_seconds)


def test_execute_shell_command_runs_low_risk_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")

    result = execute_shell_command(
        command="ls",
        cwd=tmp_path,
        policy=make_policy(tmp_path),
    )

    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.command == "ls"
    assert result.cwd == str(tmp_path)
    assert result.risk_level == "low"
    assert result.requires_confirmation is False
    assert "README.md" in result.stdout_excerpt


def test_execute_shell_command_returns_failed_for_nonzero_exit(tmp_path: Path) -> None:
    result = execute_shell_command(
        command="ls missing-file",
        cwd=tmp_path,
        policy=make_policy(tmp_path),
    )

    assert result.status == "failed"
    assert result.exit_code != 0
    assert "missing-file" in result.stderr_excerpt


def test_execute_shell_command_returns_needs_confirmation_without_running(
    tmp_path: Path,
) -> None:
    result = execute_shell_command(
        command="rm README.md",
        cwd=tmp_path,
        policy=make_policy(tmp_path),
    )

    assert result.status == "needs_confirmation"
    assert result.exit_code == -1
    assert result.requires_confirmation is True
    assert result.risk_level == "high"


def test_execute_shell_command_returns_timed_out(tmp_path: Path) -> None:
    result = execute_shell_command(
        command=f"{PYTHON} -c \"import time; time.sleep(2)\"",
        cwd=tmp_path,
        policy=make_policy(tmp_path, timeout_seconds=1),
        confirmed=True,
    )

    assert result.status == "timed_out"
    assert result.exit_code == -1
    assert result.risk_level == "medium"


def test_execute_shell_command_rejects_escaped_cwd(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    outside_path = tmp_path / "outside"
    repo_path.mkdir()
    outside_path.mkdir()

    result = execute_shell_command(
        command="ls",
        cwd=outside_path,
        policy=make_policy(repo_path),
    )

    assert result.status == "rejected"
    assert result.exit_code == -1
    assert result.stderr_excerpt == "cwd escapes allowed workspace root"
