from pathlib import Path

from app.config.settings import get_settings
from app.core.paths import ensure_data_directories


def test_settings_default_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))

    settings = get_settings()

    assert settings.project_root == tmp_path
    assert settings.data_dir == tmp_path / "data"
    assert settings.traces_dir == tmp_path / "data" / "traces"


def test_settings_uses_default_project_root_when_env_unset(monkeypatch):
    monkeypatch.delenv("MENDCODE_PROJECT_ROOT", raising=False)

    settings = get_settings()

    assert settings.project_root == Path.cwd().resolve()
    assert settings.data_dir == Path.cwd().resolve() / "data"


def test_ensure_data_directories_creates_missing_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    settings = get_settings()

    created = ensure_data_directories(settings)

    assert created == {
        "data_dir": tmp_path / "data",
        "traces_dir": tmp_path / "data" / "traces",
        "workspace_root": tmp_path / ".worktrees",
    }
    assert all(path.exists() for path in created.values())


def test_settings_exposes_workspace_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))

    settings = get_settings()

    assert settings.workspace_root == tmp_path / ".worktrees"
    assert settings.verification_timeout_seconds == 60
    assert settings.cleanup_success_workspace is False


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


def test_settings_reads_provider_values_from_project_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("MENDCODE_PROVIDER", raising=False)
    monkeypatch.delenv("MENDCODE_MODEL", raising=False)
    monkeypatch.delenv("MENDCODE_BASE_URL", raising=False)
    monkeypatch.delenv("MENDCODE_API_KEY", raising=False)
    monkeypatch.delenv("MENDCODE_PROVIDER_TIMEOUT_SECONDS", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MENDCODE_PROVIDER=openai-compatible",
                "MENDCODE_MODEL=env-file-model",
                "MENDCODE_BASE_URL=https://env-file.test/v1",
                "MENDCODE_API_KEY=env-file-key",
                "MENDCODE_PROVIDER_TIMEOUT_SECONDS=7",
            ]
        ),
        encoding="utf-8",
    )

    settings = get_settings()

    assert settings.provider == "openai-compatible"
    assert settings.provider_model == "env-file-model"
    assert settings.provider_base_url == "https://env-file.test/v1"
    assert settings.provider_api_key == "env-file-key"
    assert settings.provider_timeout_seconds == 7


def test_settings_environment_values_override_project_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MENDCODE_MODEL", "shell-model")
    monkeypatch.delenv("MENDCODE_PROVIDER", raising=False)
    monkeypatch.delenv("MENDCODE_BASE_URL", raising=False)
    monkeypatch.delenv("MENDCODE_API_KEY", raising=False)
    monkeypatch.delenv("MENDCODE_PROVIDER_TIMEOUT_SECONDS", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MENDCODE_PROVIDER=openai-compatible",
                "MENDCODE_MODEL=env-file-model",
                "MENDCODE_BASE_URL=https://env-file.test/v1",
                "MENDCODE_API_KEY=env-file-key",
            ]
        ),
        encoding="utf-8",
    )

    settings = get_settings()

    assert settings.provider == "openai-compatible"
    assert settings.provider_model == "shell-model"
    assert settings.provider_base_url == "https://env-file.test/v1"
    assert settings.provider_api_key == "env-file-key"


def test_ensure_data_directories_creates_workspace_root(monkeypatch, tmp_path):
    monkeypatch.setenv("MENDCODE_PROJECT_ROOT", str(tmp_path))
    settings = get_settings()

    created = ensure_data_directories(settings)

    assert created["workspace_root"] == tmp_path / ".worktrees"
    assert created["workspace_root"].exists()
