from pathlib import Path

from gracedays.config import load_settings


def test_mock_configuration_has_safe_defaults(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "gracedays.db"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    settings = load_settings()

    assert settings.app_name == "GraceDays"
    assert settings.llm_provider == "mock"
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8001
    assert settings.database_path.is_absolute()
    assert settings.database_path.parent.exists()
