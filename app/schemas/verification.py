from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VerificationCommandStatus = Literal["passed", "failed", "timed_out", "rejected"]
VerificationSummaryStatus = Literal["passed", "failed"]


class VerificationCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    exit_code: int
    status: VerificationCommandStatus
    duration_ms: int
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    timed_out: bool = False
    rejected: bool = False
    cwd: str

    @model_validator(mode="after")
    def validate_status_flags(self) -> "VerificationCommandResult":
        if self.status == "passed":
            if self.exit_code != 0:
                raise ValueError("passed status requires exit_code 0")
            if self.timed_out:
                raise ValueError("passed status requires timed_out=False")
            if self.rejected:
                raise ValueError("passed status requires rejected=False")
        elif self.status == "failed":
            if self.exit_code == 0:
                raise ValueError("failed status requires non-zero exit_code or launch failure")
            if self.timed_out:
                raise ValueError("failed status requires timed_out=False")
            if self.rejected:
                raise ValueError("failed status requires rejected=False")
        elif self.status == "timed_out":
            if self.exit_code != -1:
                raise ValueError("timed_out status requires exit_code -1")
            if not self.timed_out:
                raise ValueError("timed_out status requires timed_out=True")
            if self.rejected:
                raise ValueError("timed_out status requires rejected=False")
        elif self.status == "rejected":
            if self.exit_code != -1:
                raise ValueError("rejected status requires exit_code -1")
            if not self.rejected:
                raise ValueError("rejected status requires rejected=True")
            if self.timed_out:
                raise ValueError("rejected status requires timed_out=False")
        return self


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationSummaryStatus
    command_results: list[VerificationCommandResult] = Field(default_factory=list)
    passed_count: int
    failed_count: int

    @model_validator(mode="after")
    def validate_aggregate_consistency(self) -> "VerificationResult":
        passed_results = sum(1 for result in self.command_results if result.status == "passed")
        failed_results = len(self.command_results) - passed_results

        if self.passed_count != passed_results:
            raise ValueError("passed_count must match command_results")
        if self.failed_count != failed_results:
            raise ValueError("failed_count must match command_results")

        expected_status: VerificationSummaryStatus = "passed" if failed_results == 0 else "failed"
        if self.status != expected_status:
            raise ValueError("status must match command_results")

        return self
