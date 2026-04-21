from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VerificationCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str
    exit_code: int
    status: Literal["passed", "failed"]
    duration_ms: int
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "failed"]
    command_results: list[VerificationCommandResult] = Field(default_factory=list)
    passed_count: int
    failed_count: int
