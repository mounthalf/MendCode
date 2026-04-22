from pathlib import Path

from pydantic import BaseModel, ConfigDict


class CommandPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str | None = None


class CommandPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_commands: list[str]
    allowed_root: Path
    timeout_seconds: int

    def evaluate(self, command: str, cwd: Path) -> CommandPolicyDecision:
        if command not in self.allowed_commands:
            return CommandPolicyDecision(
                allowed=False,
                reason="command is not declared in verification_commands",
            )

        resolved_root = self.allowed_root.resolve()
        resolved_cwd = cwd.resolve()
        try:
            resolved_cwd.relative_to(resolved_root)
        except ValueError:
            return CommandPolicyDecision(
                allowed=False,
                reason="cwd escapes allowed workspace root",
            )

        return CommandPolicyDecision(allowed=True)
