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
