import subprocess
import time
from pathlib import Path

from app.schemas.verification import VerificationCommandResult
from app.workspace.command_policy import CommandPolicy

_OUTPUT_EXCERPT_LIMIT = 2000


def _trim_output(value: str) -> str:
    if len(value) <= _OUTPUT_EXCERPT_LIMIT:
        return value
    return value[:_OUTPUT_EXCERPT_LIMIT]


def execute_verification_command(
    command: str,
    cwd: Path,
    policy: CommandPolicy,
) -> VerificationCommandResult:
    decision = policy.evaluate(command, cwd)
    if not decision.allowed:
        return VerificationCommandResult(
            command=command,
            exit_code=-1,
            status="rejected",
            duration_ms=0,
            stdout_excerpt="",
            stderr_excerpt=decision.reason or "command rejected by policy",
            timed_out=False,
            rejected=True,
            cwd=str(cwd),
        )

    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=policy.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return VerificationCommandResult(
            command=command,
            exit_code=-1,
            status="timed_out",
            duration_ms=duration_ms,
            stdout_excerpt="",
            stderr_excerpt=f"command timed out after {policy.timeout_seconds} seconds",
            timed_out=True,
            rejected=False,
            cwd=str(cwd),
        )
    except OSError as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return VerificationCommandResult(
            command=command,
            exit_code=-1,
            status="failed",
            duration_ms=duration_ms,
            stdout_excerpt="",
            stderr_excerpt=str(exc),
            timed_out=False,
            rejected=False,
            cwd=str(cwd),
        )

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    status = "passed" if completed.returncode == 0 else "failed"
    return VerificationCommandResult(
        command=command,
        exit_code=completed.returncode,
        status=status,
        duration_ms=duration_ms,
        stdout_excerpt=_trim_output(completed.stdout),
        stderr_excerpt=_trim_output(completed.stderr),
        timed_out=False,
        rejected=False,
        cwd=str(cwd),
    )
