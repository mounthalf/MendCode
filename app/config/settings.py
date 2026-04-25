from os import getenv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app import APP_NAME, __version__

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
    provider: ProviderName = "scripted"
    provider_model: str | None = None
    provider_base_url: str | None = None
    provider_api_key: str | None = None
    provider_timeout_seconds: int = 60


def get_settings() -> Settings:
    root = Path(getenv("MENDCODE_PROJECT_ROOT", Path.cwd())).resolve()
    data_dir = root / "data"
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
