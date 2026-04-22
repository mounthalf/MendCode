import shlex
import subprocess
import sys

from app.workspace.command_policy import CommandPolicy
from app.workspace.executor import execute_verification_command

PYTHON = shlex.quote(sys.executable)


def test_execute_verification_command_returns_passed_result(tmp_path):
    policy = CommandPolicy(
        allowed_commands=[f"{PYTHON} -c \"print('ok')\""],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    result = execute_verification_command(
        command=f"{PYTHON} -c \"print('ok')\"",
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.stdout_excerpt == "ok\n"
    assert result.cwd == str(tmp_path)


def test_execute_verification_command_returns_timed_out_result(tmp_path):
    policy = CommandPolicy(
        allowed_commands=[f"{PYTHON} -c \"import time; time.sleep(2)\""],
        allowed_root=tmp_path,
        timeout_seconds=1,
    )

    result = execute_verification_command(
        command=f"{PYTHON} -c \"import time; time.sleep(2)\"",
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "timed_out"
    assert result.timed_out is True
    assert result.exit_code == -1


def test_execute_verification_command_returns_rejected_result(tmp_path):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    result = execute_verification_command(
        command="make test",
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "rejected"
    assert result.exit_code == -1
    assert result.rejected is True
    assert result.timed_out is False
    assert result.stderr_excerpt == "command is not declared in verification_commands"


def test_execute_verification_command_returns_failed_result_for_oserror(
    tmp_path, monkeypatch
):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    def fake_run(*args, **kwargs):
        raise OSError("launch failed")

    monkeypatch.setattr("app.workspace.executor.subprocess.run", fake_run)

    result = execute_verification_command(
        command="pytest -q",
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "failed"
    assert result.exit_code == -1
    assert result.timed_out is False
    assert result.rejected is False
    assert result.stderr_excerpt == "launch failed"


def test_execute_verification_command_trims_output(tmp_path):
    payload = "x" * 2100
    script = f"import sys; sys.stdout.write({payload!r})"
    command = f"{PYTHON} -c {shlex.quote(script)}"
    policy = CommandPolicy(
        allowed_commands=[command],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    result = execute_verification_command(
        command=command,
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "passed"
    assert result.stdout_excerpt == payload[:2000]
    assert len(result.stdout_excerpt) == 2000


def test_execute_verification_command_preserves_partial_timeout_output(
    tmp_path, monkeypatch
):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=1,
    )

    exc = subprocess.TimeoutExpired(
        cmd="pytest -q",
        timeout=1,
        output=("o" * 2100).encode(),
        stderr=("e" * 2101).encode(),
    )

    def fake_run(*args, **kwargs):
        raise exc

    monkeypatch.setattr("app.workspace.executor.subprocess.run", fake_run)

    result = execute_verification_command(
        command="pytest -q",
        cwd=tmp_path,
        policy=policy,
    )

    assert result.status == "timed_out"
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.stdout_excerpt == "o" * 2000
    assert result.stderr_excerpt == "e" * 2000
