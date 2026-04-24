from app.orchestrator.failure_parser import extract_failure_insight
from app.schemas.verification import VerificationCommandResult


def build_failed_command(stdout: str = "", stderr: str = "") -> VerificationCommandResult:
    return VerificationCommandResult(
        command="python -m pytest -q",
        exit_code=1,
        status="failed",
        duration_ms=12,
        stdout_excerpt=stdout,
        stderr_excerpt=stderr,
        timed_out=False,
        rejected=False,
        cwd="/repo",
    )


def test_extract_failure_insight_from_pytest_failed_line():
    command = build_failed_command(
        stdout=(
            "FAILED tests/test_calculator.py::test_add - "
            "AssertionError: assert -1 == 5\n"
        )
    )

    insight = extract_failure_insight([command])

    assert insight is not None
    assert insight.command == "python -m pytest -q"
    assert insight.failed_node == "tests/test_calculator.py::test_add"
    assert insight.file_path == "tests/test_calculator.py"
    assert insight.test_name == "test_add"
    assert insight.error_summary == "AssertionError: assert -1 == 5"


def test_extract_failure_insight_prefers_first_non_passed_command():
    rejected = VerificationCommandResult(
        command="python -m pytest -q",
        exit_code=-1,
        status="rejected",
        duration_ms=0,
        stdout_excerpt="",
        stderr_excerpt="command rejected by policy",
        timed_out=False,
        rejected=True,
        cwd="/repo",
    )

    insight = extract_failure_insight([rejected])

    assert insight is not None
    assert insight.command == "python -m pytest -q"
    assert insight.failed_node is None
    assert insight.error_summary == "command rejected by policy"
