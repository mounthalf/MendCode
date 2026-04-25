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
