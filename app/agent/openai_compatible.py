import json
import re
from typing import Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agent.provider import AgentProviderStepInput, ProviderResponse
from app.schemas.agent_action import parse_mendcode_action


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class OpenAICompatibleClient(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_seconds: int,
    ) -> str:
        ...


class OpenAIChatCompletionsClient:
    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_seconds: int,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=[message.model_dump() for message in messages],
            timeout=timeout_seconds,
        )
        content = response.choices[0].message.content
        return content or ""


_JSON_FENCE = re.compile(r"^```(?:json)?\s*(?P<body>.*?)\s*```$", re.DOTALL)


def redact_secret(message: str, secret: str | None) -> str:
    if not secret:
        return message
    return message.replace(secret, "[REDACTED]")


def extract_action_json(text: str) -> dict[str, object]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty response")
    fence_match = _JSON_FENCE.match(stripped)
    if fence_match is not None:
        stripped = fence_match.group("body").strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("action JSON must be an object")
    return parsed


class OpenAICompatibleAgentProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        timeout_seconds: int,
        client: OpenAICompatibleClient | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._client = client or OpenAIChatCompletionsClient(
            api_key=api_key,
            base_url=base_url,
        )

    def next_action(self, step_input: AgentProviderStepInput) -> ProviderResponse:
        try:
            content = self._client.complete(
                model=self._model,
                messages=self._build_messages(step_input),
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            return ProviderResponse.failed(
                f"Provider request failed: {redact_secret(str(exc), self._api_key)}"
            )
        if not content.strip():
            return ProviderResponse.failed("Provider returned empty response")
        try:
            payload = extract_action_json(content)
        except (json.JSONDecodeError, ValueError):
            return ProviderResponse.failed("Provider returned invalid JSON action")
        try:
            parse_mendcode_action(payload)
        except ValidationError:
            return ProviderResponse.failed("Provider returned invalid MendCode action")
        return ProviderResponse(status="succeeded", actions=[payload])

    def _build_messages(self, step_input: AgentProviderStepInput) -> list[ChatMessage]:
        system_prompt = (
            "You are MendCode's action planner. Return exactly one JSON object and no prose. "
            "The object must be a valid MendCodeAction. Allowed tool actions: repo_status, "
            "detect_project, run_command, read_file, search_code, apply_patch_to_worktree, "
            "show_diff."
        )
        user_prompt = json.dumps(
            {
                "problem_statement": step_input.problem_statement,
                "verification_commands": step_input.verification_commands,
                "step_index": step_input.step_index,
                "remaining_steps": step_input.remaining_steps,
                "observations": [
                    record.model_dump(mode="json") for record in step_input.observations
                ],
            },
            ensure_ascii=False,
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
