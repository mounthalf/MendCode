import subprocess
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.workspace.shell_policy import ShellPolicy, ShellRiskLevel

_OUTPUT_EXCERPT_LIMIT = 2000

ShellCommandStatus = Literal[
    "passed",
    "failed",
    "timed_out",
    "rejected",
    "needs_confirmation",
]


class ShellCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    cwd: str
    exit_code: int
    status: ShellCommandStatus
    stdout_excerpt: str
    stderr_excerpt: str
    duration_ms: int
    risk_level: ShellRiskLevel
    requires_confirmation: bool


def _coerce_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _trim_output(value: str | bytes | None) -> str:
    text = _coerce_output_text(value)
    if len(text) <= _OUTPUT_EXCERPT_LIMIT:
        return text
    return text[:_OUTPUT_EXCERPT_LIMIT]


def execute_shell_command(
    *,
    command: str,
    cwd: Path,
    policy: ShellPolicy,
    confirmed: bool = False,
) -> ShellCommandResult:
    decision = policy.evaluate(command, cwd)
    if decision.requires_confirmation and not confirmed:
        return ShellCommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=-1,
            status="needs_confirmation",
            stdout_excerpt="",
            stderr_excerpt=decision.reason or "command requires confirmation",
            duration_ms=0,
            risk_level=decision.risk_level,
            requires_confirmation=True,
        )
    if not decision.allowed and not decision.requires_confirmation:
        return ShellCommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=-1,
            status="rejected",
            stdout_excerpt="",
            stderr_excerpt=decision.reason or "command rejected by shell policy",
            duration_ms=0,
            risk_level=decision.risk_level,
            requires_confirmation=False,
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
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        timeout_message = f"command timed out after {policy.timeout_seconds} seconds"
        return ShellCommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=-1,
            status="timed_out",
            stdout_excerpt=_trim_output(exc.output),
            stderr_excerpt=_trim_output(exc.stderr) or timeout_message,
            duration_ms=duration_ms,
            risk_level=decision.risk_level,
            requires_confirmation=decision.requires_confirmation,
        )
    except OSError as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return ShellCommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=-1,
            status="failed",
            stdout_excerpt="",
            stderr_excerpt=str(exc),
            duration_ms=duration_ms,
            risk_level=decision.risk_level,
            requires_confirmation=decision.requires_confirmation,
        )

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    return ShellCommandResult(
        command=command,
        cwd=str(cwd),
        exit_code=completed.returncode,
        status="passed" if completed.returncode == 0 else "failed",
        stdout_excerpt=_trim_output(completed.stdout),
        stderr_excerpt=_trim_output(completed.stderr),
        duration_ms=duration_ms,
        risk_level=decision.risk_level,
        requires_confirmation=decision.requires_confirmation,
    )
