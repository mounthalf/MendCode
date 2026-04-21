from typing import Literal

from pydantic import BaseModel, ConfigDict


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    task_type: Literal["ci_fix", "test_regression_fix", "pr_review"]
    status: Literal["running", "completed", "failed"]
    current_step: Literal["bootstrap", "summarize"]
    summary: str
    trace_path: str
