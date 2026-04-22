import shlex
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
