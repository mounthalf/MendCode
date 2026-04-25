# OpenAI-Compatible JSON Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional OpenAI-compatible JSON Action provider that can drive the existing provider-driven Agent loop while keeping `scripted` as the default path.

**Architecture:** Provider configuration lives in `app/config/settings.py` and is selected by a small factory in `app/agent/provider_factory.py`. The OpenAI-compatible implementation lives in `app/agent/openai_compatible.py`, owns prompt building, client calls, JSON extraction, action validation, and API-key redaction. `app/agent/loop.py` remains provider-format agnostic.

**Tech Stack:** Python 3.11, Pydantic v2, OpenAI Python SDK dependency already listed in `pyproject.toml`, Typer, Rich, pytest, ruff.

---

## File Structure

- Modify `app/config/settings.py`
  - Add provider environment settings.
  - Keep default provider as `scripted`.

- Create `app/agent/openai_compatible.py`
  - Define `ChatMessage`.
  - Define `OpenAICompatibleClient` protocol.
  - Define `OpenAIChatCompletionsClient`.
  - Define `OpenAICompatibleAgentProvider`.
  - Implement JSON extraction and API-key redaction.

- Create `app/agent/provider_factory.py`
  - Define `ProviderConfigurationError`.
  - Implement `build_agent_provider(settings)`.

- Modify `app/cli/main.py`
  - Use `build_agent_provider(settings)` instead of directly instantiating `ScriptedAgentProvider`.
  - Preserve pre-loop provider failure behavior for missing `--test`.
  - Print provider configuration errors without exposing secrets.

- Modify `tests/unit/test_settings.py`
  - Cover default scripted provider settings.
  - Cover openai-compatible environment settings.

- Create `tests/unit/test_openai_compatible_provider.py`
  - Cover fake-client success and failure paths.
  - Cover JSON parsing and redaction.

- Create `tests/unit/test_provider_factory.py`
  - Cover default scripted provider construction.
  - Cover missing openai-compatible config errors.
  - Cover openai-compatible construction with a fake client factory.

- Modify `tests/integration/test_cli.py`
  - Cover default scripted path remains unchanged.
  - Cover CLI provider configuration failure path.

- Modify docs after implementation:
  - `README.md`
  - `MendCode_开发方案.md`
  - `MendCode_全局路线图.md`
  - `MendCode_TUI产品基调与交互方案.md`

---

### Task 1: Provider Settings

**Files:**
- Modify: `app/config/settings.py`
- Test: `tests/unit/test_settings.py`

- [ ] **Step 1: Write failing settings tests**

Add these tests to `tests/unit/test_settings.py`:

```python
def test_settings_default_provider_is_scripted(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("MENDCODE_PROVIDER", raising=False)
    monkeypatch.delenv("MENDCODE_MODEL", raising=False)
    monkeypatch.delenv("MENDCODE_BASE_URL", raising=False)
    monkeypatch.delenv("MENDCODE_API_KEY", raising=False)
    monkeypatch.delenv("MENDCODE_PROVIDER_TIMEOUT_SECONDS", raising=False)

    settings = get_settings()

    assert settings.provider == "scripted"
    assert settings.provider_model is None
    assert settings.provider_base_url is None
    assert settings.provider_api_key is None
    assert settings.provider_timeout_seconds == 60
```

Add:

```python
def test_settings_reads_openai_compatible_provider_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MENDCODE_PROVIDER", "openai-compatible")
    monkeypatch.setenv("MENDCODE_MODEL", "test-model")
    monkeypatch.setenv("MENDCODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MENDCODE_API_KEY", "secret-key")
    monkeypatch.setenv("MENDCODE_PROVIDER_TIMEOUT_SECONDS", "12")

    settings = get_settings()

    assert settings.provider == "openai-compatible"
    assert settings.provider_model == "test-model"
    assert settings.provider_base_url == "https://example.test/v1"
    assert settings.provider_api_key == "secret-key"
    assert settings.provider_timeout_seconds == 12
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/unit/test_settings.py -q
```

Expected: FAIL because provider fields do not exist on `Settings`.

- [ ] **Step 3: Implement provider settings**

Update `app/config/settings.py`:

```python
from typing import Literal

ProviderName = Literal["scripted", "openai-compatible"]


class Settings(BaseModel):
    app_name: str
    app_version: str
    project_root: Path
    data_dir: Path
    traces_dir: Path
    workspace_root: Path
    verification_timeout_seconds: int
    cleanup_success_workspace: bool
    provider: ProviderName
    provider_model: str | None
    provider_base_url: str | None
    provider_api_key: str | None
    provider_timeout_seconds: int
```

Update `get_settings()`:

```python
provider = getenv("MENDCODE_PROVIDER", "scripted")
return Settings(
    app_name=APP_NAME,
    app_version=__version__,
    project_root=root,
    data_dir=data_dir,
    traces_dir=data_dir / "traces",
    workspace_root=root / ".worktrees",
    verification_timeout_seconds=60,
    cleanup_success_workspace=False,
    provider=provider,  # type: ignore[arg-type]
    provider_model=getenv("MENDCODE_MODEL"),
    provider_base_url=getenv("MENDCODE_BASE_URL"),
    provider_api_key=getenv("MENDCODE_API_KEY"),
    provider_timeout_seconds=int(getenv("MENDCODE_PROVIDER_TIMEOUT_SECONDS", "60")),
)
```

- [ ] **Step 4: Run settings tests**

Run:

```bash
python -m pytest tests/unit/test_settings.py -q
```

Expected: PASS.

---

### Task 2: OpenAI-Compatible Provider JSON Parsing And Fake Client

**Files:**
- Create: `app/agent/openai_compatible.py`
- Test: `tests/unit/test_openai_compatible_provider.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/unit/test_openai_compatible_provider.py`:

```python
from app.agent.openai_compatible import (
    ChatMessage,
    OpenAICompatibleAgentProvider,
    extract_action_json,
    redact_secret,
)
from app.agent.provider import AgentProviderStepInput


class FakeClient:
    def __init__(self, response: str | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        timeout_seconds: int,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.exc is not None:
            raise self.exc
        return self.response or ""


def step_input() -> AgentProviderStepInput:
    return AgentProviderStepInput(
        problem_statement="inspect repo",
        verification_commands=["python -m pytest -q"],
        step_index=1,
        remaining_steps=4,
        observations=[],
    )


def test_extract_action_json_accepts_plain_object() -> None:
    text = '{"type":"tool_call","action":"repo_status","reason":"inspect","args":{}}'

    assert extract_action_json(text) == {
        "type": "tool_call",
        "action": "repo_status",
        "reason": "inspect",
        "args": {},
    }


def test_extract_action_json_accepts_single_json_fence() -> None:
    text = '```json\n{"type":"final_response","status":"completed","summary":"done"}\n```'

    assert extract_action_json(text) == {
        "type": "final_response",
        "status": "completed",
        "summary": "done",
    }


def test_openai_compatible_provider_returns_action_from_fake_client() -> None:
    client = FakeClient(
        '{"type":"tool_call","action":"repo_status","reason":"inspect","args":{}}'
    )
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=client,
    )

    response = provider.next_action(step_input())

    assert response.status == "succeeded"
    assert response.action == {
        "type": "tool_call",
        "action": "repo_status",
        "reason": "inspect",
        "args": {},
    }
    assert client.calls[0]["model"] == "test-model"
    assert client.calls[0]["timeout_seconds"] == 12
```

Add failure-path tests:

```python
def test_openai_compatible_provider_rejects_empty_response() -> None:
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=FakeClient(""),
    )

    response = provider.next_action(step_input())

    assert response.status == "failed"
    assert response.observation is not None
    assert response.observation.error_message == "Provider returned empty response"


def test_openai_compatible_provider_rejects_invalid_json() -> None:
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=FakeClient("not json"),
    )

    response = provider.next_action(step_input())

    assert response.status == "failed"
    assert response.observation is not None
    assert response.observation.error_message == "Provider returned invalid JSON action"


def test_openai_compatible_provider_rejects_invalid_action_schema() -> None:
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=FakeClient('{"type":"tool_call","action":"delete_repo"}'),
    )

    response = provider.next_action(step_input())

    assert response.status == "failed"
    assert response.observation is not None
    assert response.observation.error_message == "Provider returned invalid MendCode action"


def test_openai_compatible_provider_redacts_api_key_from_client_errors() -> None:
    provider = OpenAICompatibleAgentProvider(
        model="test-model",
        api_key="secret-key",
        base_url="https://example.test/v1",
        timeout_seconds=12,
        client=FakeClient(exc=RuntimeError("bad secret-key failure")),
    )

    response = provider.next_action(step_input())

    assert response.status == "failed"
    assert response.observation is not None
    assert response.observation.error_message == "Provider request failed: bad [REDACTED] failure"


def test_redact_secret_replaces_secret_value() -> None:
    assert redact_secret("token secret-key leaked", "secret-key") == "token [REDACTED] leaked"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/unit/test_openai_compatible_provider.py -q
```

Expected: FAIL because `app.agent.openai_compatible` does not exist.

- [ ] **Step 3: Implement provider and parser**

Create `app/agent/openai_compatible.py` with:

```python
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
```

Add helpers:

```python
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
```

Add provider:

```python
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
            "detect_project, run_command, read_file, search_code, apply_patch_to_worktree, show_diff."
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
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
python -m pytest tests/unit/test_openai_compatible_provider.py -q
```

Expected: PASS.

---

### Task 3: Provider Factory

**Files:**
- Create: `app/agent/provider_factory.py`
- Test: `tests/unit/test_provider_factory.py`

- [ ] **Step 1: Write failing provider factory tests**

Create `tests/unit/test_provider_factory.py`:

```python
from pathlib import Path

from app.agent.openai_compatible import OpenAICompatibleAgentProvider
from app.agent.provider import ScriptedAgentProvider
from app.agent.provider_factory import ProviderConfigurationError, build_agent_provider
from app.config.settings import Settings


def settings_for(
    tmp_path: Path,
    *,
    provider: str = "scripted",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Settings:
    return Settings(
        app_name="MendCode",
        app_version="0.0.0",
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        traces_dir=tmp_path / "data" / "traces",
        workspace_root=tmp_path / ".worktrees",
        verification_timeout_seconds=60,
        cleanup_success_workspace=False,
        provider=provider,  # type: ignore[arg-type]
        provider_model=model,
        provider_base_url=base_url,
        provider_api_key=api_key,
        provider_timeout_seconds=60,
    )


def test_build_agent_provider_defaults_to_scripted(tmp_path: Path) -> None:
    provider = build_agent_provider(settings_for(tmp_path))

    assert isinstance(provider, ScriptedAgentProvider)


def test_build_agent_provider_rejects_missing_openai_compatible_config(tmp_path: Path) -> None:
    try:
        build_agent_provider(settings_for(tmp_path, provider="openai-compatible"))
    except ProviderConfigurationError as exc:
        assert str(exc) == (
            "openai-compatible provider requires MENDCODE_MODEL, "
            "MENDCODE_BASE_URL, and MENDCODE_API_KEY"
        )
    else:
        raise AssertionError("missing openai-compatible config was accepted")


def test_build_agent_provider_constructs_openai_compatible_provider(tmp_path: Path) -> None:
    provider = build_agent_provider(
        settings_for(
            tmp_path,
            provider="openai-compatible",
            model="test-model",
            base_url="https://example.test/v1",
            api_key="secret-key",
        )
    )

    assert isinstance(provider, OpenAICompatibleAgentProvider)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/unit/test_provider_factory.py -q
```

Expected: FAIL because provider factory does not exist.

- [ ] **Step 3: Implement provider factory**

Create `app/agent/provider_factory.py`:

```python
from app.agent.openai_compatible import OpenAICompatibleAgentProvider
from app.agent.provider import AgentProvider, ScriptedAgentProvider
from app.config.settings import Settings


class ProviderConfigurationError(ValueError):
    pass


def build_agent_provider(settings: Settings) -> AgentProvider:
    if settings.provider == "scripted":
        return ScriptedAgentProvider()

    if settings.provider == "openai-compatible":
        if (
            not settings.provider_model
            or not settings.provider_base_url
            or not settings.provider_api_key
        ):
            raise ProviderConfigurationError(
                "openai-compatible provider requires MENDCODE_MODEL, "
                "MENDCODE_BASE_URL, and MENDCODE_API_KEY"
            )
        return OpenAICompatibleAgentProvider(
            model=settings.provider_model,
            api_key=settings.provider_api_key,
            base_url=settings.provider_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    raise ProviderConfigurationError(f"unsupported provider: {settings.provider}")
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
python -m pytest tests/unit/test_provider_factory.py -q
```

Expected: PASS.

---

### Task 4: CLI Provider Selection

**Files:**
- Modify: `app/cli/main.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing CLI config error test**

Add to `tests/integration/test_cli.py`:

```python
def test_fix_command_reports_provider_configuration_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MENDCODE_PROVIDER", "openai-compatible")
    monkeypatch.delenv("MENDCODE_MODEL", raising=False)
    monkeypatch.delenv("MENDCODE_BASE_URL", raising=False)
    monkeypatch.delenv("MENDCODE_API_KEY", raising=False)
    monkeypatch.setattr("app.cli.main.console.width", 200, raising=False)
    repo_path = init_git_repo(tmp_path)

    result = runner.invoke(
        app,
        [
            "fix",
            "修复 pytest 失败",
            "--test",
            f"{PYTHON} -c \"raise SystemExit(0)\"",
            "--repo",
            str(repo_path),
        ],
        terminal_width=200,
    )

    assert result.exit_code != 0
    assert "Provider Configuration" in result.stdout
    assert "MENDCODE_MODEL" in result.stdout
    assert "agent-" not in result.stdout
```

- [ ] **Step 2: Run CLI test to verify RED**

Run:

```bash
python -m pytest tests/integration/test_cli.py::test_fix_command_reports_provider_configuration_error -q
```

Expected: FAIL because CLI does not use provider factory.

- [ ] **Step 3: Update CLI to use provider factory**

In `app/cli/main.py`, replace direct `ScriptedAgentProvider()` construction:

```python
from app.agent.provider_factory import ProviderConfigurationError, build_agent_provider
```

Inside `fix_problem()`:

```python
try:
    provider = build_agent_provider(settings)
except ProviderConfigurationError as exc:
    table = Table(title="Provider Configuration")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("status", "failed")
    table.add_row("error", str(exc))
    console.print(table)
    raise typer.Exit(code=1)
```

Keep:

```python
provider_response = provider.plan_actions(...)
```

only for providers that support `plan_actions`. To avoid requiring `plan_actions` on real providers, replace the pre-loop missing-test validation with:

```python
if not test_commands:
    table = Table(title="Agent Fix")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("problem_statement", problem_statement)
    table.add_row("status", "failed")
    table.add_row("summary", "Provider failed")
    table.add_row("error", "at least one verification command is required")
    console.print(table)
    raise typer.Exit(code=1)
```

Then remove `provider_response = provider.plan_actions(...)` from the main path and use `provider` directly in `AgentLoopInput`.

For failure-location context, keep a local `ScriptedAgentProvider()` for `plan_failure_location_actions()` because that remains deterministic and separate from real provider selection in this slice.

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -m pytest tests/integration/test_cli.py -q
```

Expected: PASS.

---

### Task 5: Documentation And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `MendCode_开发方案.md`
- Modify: `MendCode_全局路线图.md`
- Modify: `MendCode_TUI产品基调与交互方案.md`

- [ ] **Step 1: Update docs**

Update docs to state:

- OpenAI-compatible provider adapter exists.
- It uses JSON MendCode Action output, not native tool calling.
- `scripted` remains default.
- Environment variables:

```bash
MENDCODE_PROVIDER=openai-compatible
MENDCODE_MODEL=<model>
MENDCODE_BASE_URL=<base-url>
MENDCODE_API_KEY=<key>
```

Keep unchecked:

- Anthropic adapter.
- OpenAI native adapter.
- TUI provider UI.
- apply/discard.
- real LLM patch proposal guarantee.

- [ ] **Step 2: Run focused tests**

Run:

```bash
python -m pytest tests/unit/test_settings.py tests/unit/test_openai_compatible_provider.py tests/unit/test_provider_factory.py tests/integration/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
python -m pytest -q
ruff check .
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Review diff**

Run:

```bash
git diff --stat
git diff -- app/config/settings.py app/agent/openai_compatible.py app/agent/provider_factory.py app/cli/main.py
```

Expected: changes are limited to provider configuration, provider adapter, provider factory, CLI selection, tests, docs, and this plan.

- [ ] **Step 5: Commit**

Run:

```bash
git add app/config/settings.py app/agent/openai_compatible.py app/agent/provider_factory.py app/cli/main.py tests/unit/test_settings.py tests/unit/test_openai_compatible_provider.py tests/unit/test_provider_factory.py tests/integration/test_cli.py README.md MendCode_开发方案.md MendCode_全局路线图.md MendCode_TUI产品基调与交互方案.md docs/superpowers/plans/2026-04-25-openai-compatible-json-provider.md
git commit -m "feat: add openai-compatible json provider"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: The plan covers environment settings, default scripted provider, openai-compatible provider construction, fake-client tests, JSON extraction, invalid response failures, key redaction, CLI provider selection, docs, focused tests, full tests, lint, and whitespace checks.
- Scope control: The plan does not add TUI, apply/discard, Anthropic, native tool calling, config files, keyring, streaming, or real network tests.
- Type consistency: `OpenAICompatibleAgentProvider`, `OpenAICompatibleClient`, `ChatMessage`, `ProviderConfigurationError`, `build_agent_provider`, and provider setting names are consistent across tasks.
