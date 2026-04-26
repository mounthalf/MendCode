from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config.settings import Settings
from app.schemas.agent_action import Observation


ToolInvocationSource = Literal["openai_tool_call", "json_action"]


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    WRITE_WORKTREE = "write_worktree"
    SHELL_RESTRICTED = "shell_restricted"
    DANGEROUS = "dangerous"


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    source: ToolInvocationSource
    group_id: str | None = None

    @model_validator(mode="after")
    def validate_name(self) -> "ToolInvocation":
        if not self.name.strip():
            raise ValueError("tool invocation name must not be empty")
        return self


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    workspace_path: Path
    settings: Settings
    verification_commands: list[str] = Field(default_factory=list)


ToolExecutor = Callable[[BaseModel, ToolExecutionContext], Observation]


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str
    description: str
    args_model: type[BaseModel]
    risk_level: ToolRisk
    executor: ToolExecutor

    @model_validator(mode="after")
    def validate_spec(self) -> "ToolSpec":
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        return self

    def execute(self, args: dict[str, Any], context: ToolExecutionContext) -> Observation:
        try:
            parsed_args = self.args_model.model_validate(args)
        except ValidationError as exc:
            return Observation(
                status="rejected",
                summary="Invalid tool arguments",
                payload={"tool_name": self.name, "args": args},
                error_message=str(exc),
            )
        return self.executor(parsed_args, context)

    def to_openai_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._specs)

    def openai_tools(self) -> list[dict[str, object]]:
        return [self._specs[name].to_openai_tool() for name in self.names()]
