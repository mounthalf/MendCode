from os import getenv
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel

from app import APP_NAME, __version__

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ProviderName = Literal["scripted", "openai-compatible"]


def _setting_value(
    name: str,
    env_file_values: dict[str, str | None],
    default: str | None = None,
) -> str | None:
    env_value = getenv(name)
    if env_value is not None:
        return env_value
    return env_file_values.get(name) or default


class Settings(BaseModel):
    app_name: str
    app_version: str
    project_root: Path
    data_dir: Path
    traces_dir: Path
    workspace_root: Path
    verification_timeout_seconds: int
    cleanup_success_workspace: bool
    provider: ProviderName = "scripted"
    provider_model: str | None = None
    provider_base_url: str | None = None
    provider_api_key: str | None = None
    provider_timeout_seconds: int = 60


def get_settings() -> Settings:
    root = Path(getenv("MENDCODE_PROJECT_ROOT", Path.cwd())).resolve()
    data_dir = root / "data"
    env_file_values = dotenv_values(root / ".env")
    provider = _setting_value("MENDCODE_PROVIDER", env_file_values, "scripted")
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
        provider_model=_setting_value("MENDCODE_MODEL", env_file_values),
        provider_base_url=_setting_value("MENDCODE_BASE_URL", env_file_values),
        provider_api_key=_setting_value("MENDCODE_API_KEY", env_file_values),
        provider_timeout_seconds=int(
            _setting_value("MENDCODE_PROVIDER_TIMEOUT_SECONDS", env_file_values, "60")
            or "60"
        ),
    )
