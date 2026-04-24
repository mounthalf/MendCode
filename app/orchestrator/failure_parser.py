import re
from dataclasses import dataclass

from app.schemas.verification import VerificationCommandResult

_PYTEST_FAILED_LINE = re.compile(
    r"FAILED\s+(?P<node>\S+?::(?P<test>[^\s:]+))(?:\s+-\s+(?P<error>.+))?$"
)


@dataclass(frozen=True)
class FailureInsight:
    command: str
    status: str
    failed_node: str | None
    file_path: str | None
    test_name: str | None
    error_summary: str

    def as_payload(self) -> dict[str, str | None]:
        return {
            "command": self.command,
            "status": self.status,
            "failed_node": self.failed_node,
            "file_path": self.file_path,
            "test_name": self.test_name,
            "error_summary": self.error_summary,
        }


def _combined_output(result: VerificationCommandResult) -> str:
    return "\n".join(
        part
        for part in [result.stdout_excerpt, result.stderr_excerpt]
        if part
    )


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def extract_failure_insight(
    command_results: list[VerificationCommandResult],
) -> FailureInsight | None:
    result = next((item for item in command_results if item.status != "passed"), None)
    if result is None:
        return None

    output = _combined_output(result)
    failed_node: str | None = None
    file_path: str | None = None
    test_name: str | None = None
    error_summary = _first_meaningful_line(output)

    for line in output.splitlines():
        match = _PYTEST_FAILED_LINE.search(line.strip())
        if match is None:
            continue
        failed_node = match.group("node")
        file_path = failed_node.split("::", 1)[0]
        test_name = match.group("test")
        error_summary = (match.group("error") or error_summary).strip()
        break

    return FailureInsight(
        command=result.command,
        status=result.status,
        failed_node=failed_node,
        file_path=file_path,
        test_name=test_name,
        error_summary=error_summary,
    )
