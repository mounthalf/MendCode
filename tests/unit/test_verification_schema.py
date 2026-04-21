import pytest
from pydantic import ValidationError

from app.schemas.verification import VerificationCommandResult, VerificationResult


def test_verification_result_serializes_expected_fields():
    result = VerificationResult(
        status="failed",
        passed_count=1,
        failed_count=1,
        command_results=[
            VerificationCommandResult(
                command="pytest -q",
                exit_code=0,
                status="passed",
                duration_ms=120,
                stdout_excerpt="2 passed",
                stderr_excerpt="",
            ),
            VerificationCommandResult(
                command="python -m bad.module",
                exit_code=1,
                status="failed",
                duration_ms=80,
                stdout_excerpt="",
                stderr_excerpt="ModuleNotFoundError",
            ),
        ],
    )

    assert result.model_dump() == {
        "status": "failed",
        "command_results": [
            {
                "command": "pytest -q",
                "exit_code": 0,
                "status": "passed",
                "duration_ms": 120,
                "stdout_excerpt": "2 passed",
                "stderr_excerpt": "",
            },
            {
                "command": "python -m bad.module",
                "exit_code": 1,
                "status": "failed",
                "duration_ms": 80,
                "stdout_excerpt": "",
                "stderr_excerpt": "ModuleNotFoundError",
            },
        ],
        "passed_count": 1,
        "failed_count": 1,
    }


def test_verification_schema_rejects_invalid_status():
    with pytest.raises(ValidationError):
        VerificationCommandResult(
            command="pytest -q",
            exit_code=0,
            status="unknown",
            duration_ms=100,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )
