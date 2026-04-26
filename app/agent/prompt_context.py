import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.provider import AgentObservationRecord, AgentProviderStepInput


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class PromptContextLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_text_chars: int = Field(default=2000, ge=1)
    max_observations: int = Field(default=12, ge=1)
    max_search_matches: int = Field(default=8, ge=0)


def _redact_text(value: str, secret_values: list[str]) -> str:
    redacted = value
    for secret in secret_values:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _trim_text(value: object, *, limits: PromptContextLimits, secret_values: list[str]) -> str:
    text = _redact_text(str(value), secret_values)
    if len(text) <= limits.max_text_chars:
        return text
    return text[: limits.max_text_chars] + "...[truncated]"


def _selected_payload(
    payload: dict[str, Any],
    *,
    limits: PromptContextLimits,
    secret_values: list[str],
) -> dict[str, object]:
    selected: dict[str, object] = {}
    for key in [
        "command",
        "status",
        "exit_code",
        "relative_path",
        "file_path",
        "failed_node",
        "test_name",
        "stderr_excerpt",
        "stdout_excerpt",
        "error_summary",
        "diff_stat",
        "content",
        "truncated",
        "pattern",
        "total_entries",
        "total_matches",
    ]:
        if key in payload:
            selected[key] = _trim_text(
                payload[key],
                limits=limits,
                secret_values=secret_values,
            )
    entries = payload.get("entries")
    if isinstance(entries, list):
        selected["entries"] = [
            {
                str(entry_key): _trim_text(
                    entry_value,
                    limits=limits,
                    secret_values=secret_values,
                )
                for entry_key, entry_value in entry.items()
            }
            for entry in entries[: limits.max_search_matches]
            if isinstance(entry, dict)
        ]
        selected["entries_truncated"] = len(entries) > limits.max_search_matches
    matches = payload.get("matches")
    if isinstance(matches, list):
        selected["matches"] = [
            {
                str(match_key): _trim_text(
                    match_value,
                    limits=limits,
                    secret_values=secret_values,
                )
                for match_key, match_value in match.items()
            }
            for match in matches[: limits.max_search_matches]
            if isinstance(match, dict)
        ]
        selected["matches_truncated"] = len(matches) > limits.max_search_matches
    return selected


def summarize_observation_record(
    record: AgentObservationRecord,
    *,
    limits: PromptContextLimits,
    secret_values: list[str],
) -> dict[str, object]:
    action = record.action
    action_payload: dict[str, object] | None = None
    if action is not None:
        action_payload = action.model_dump(mode="json")
    observation = record.observation
    return {
        "action_type": action.type if action is not None else None,
        "tool_name": getattr(action, "action", None) if action is not None else None,
        "action": action_payload,
        "status": observation.status,
        "summary": _trim_text(
            observation.summary,
            limits=limits,
            secret_values=secret_values,
        ),
        "error_message": (
            _trim_text(
                observation.error_message,
                limits=limits,
                secret_values=secret_values,
            )
            if observation.error_message is not None
            else None
        ),
        "payload": _selected_payload(
            observation.payload,
            limits=limits,
            secret_values=secret_values,
        ),
    }


def _system_prompt() -> str:
    return (
        "You are MendCode's action planner. Return exactly one JSON object and no prose. "
        "The object must be a valid MendCodeAction.\n"
        "Allowed action types: assistant_message, tool_call, patch_proposal, "
        "user_confirmation_request, final_response.\n"
        "Allowed tool actions: repo_status, detect_project, read_file, list_dir, "
        "glob_file_search, search_code, rg, git, apply_patch, apply_patch_to_worktree, "
        "show_diff, run_shell_command, run_command.\n"
        "Use the discriminator field named type. Do not use action_type. Examples: "
        '{"type": "tool_call", "action": "repo_status", "reason": "inspect", "args": {}}; '
        '{"type": "final_response", "status": "completed", "summary": "verified", '
        '"recommended_actions": []}.\n'
        "Prefer structured tools over raw shell: use read_file for file content, "
        "list_dir for directory inspection, glob_file_search for path discovery, rg or "
        "search_code for text search, git for repository inspection, and apply_patch for "
        "unified diffs. Use run_shell_command only when no structured tool fits. Use "
        "run_command only for declared verification commands from verification_commands.\n"
        "Repair workflow: inspect repo status and project type if unknown; run or inspect "
        "verification failure; read failing test files; search candidate implementation; "
        "propose a unified diff patch with patch_proposal; rerun verification; show_diff; "
        "then return final_response.\n"
        'Never claim completed after a failed verification. Use "status": "failed" when '
        "the repair is not verified or the step budget is low."
    )


def build_provider_messages(
    step_input: AgentProviderStepInput,
    *,
    limits: PromptContextLimits | None = None,
    secret_values: list[str] | None = None,
) -> list[ChatMessage]:
    context_limits = limits or PromptContextLimits()
    secrets = secret_values or []
    observations = [
        summarize_observation_record(
            record,
            limits=context_limits,
            secret_values=secrets,
        )
        for record in step_input.observations[-context_limits.max_observations :]
    ]
    user_context = {
        "problem_statement": _trim_text(
            step_input.problem_statement,
            limits=context_limits,
            secret_values=secrets,
        ),
        "verification_commands": [
            _trim_text(command, limits=context_limits, secret_values=secrets)
            for command in step_input.verification_commands
        ],
        "step_index": step_input.step_index,
        "remaining_steps": step_input.remaining_steps,
        "observations": observations,
    }
    return [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(
            role="user",
            content=json.dumps(user_context, ensure_ascii=False, sort_keys=True),
        ),
    ]
