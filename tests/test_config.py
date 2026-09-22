import pytest

from apps.api import config


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch, tmp_path):
    for name in ("APP_ENV", "DATABASE_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    config.get_settings.cache_clear()
    yield tmp_path
    config.get_settings.cache_clear()


def test_default_uses_only_local_file(clean_settings):
    (clean_settings / ".env.local").write_text(
        "DATABASE_URL=postgresql://user:local@localhost/dev\n"
    )
    (clean_settings / ".env.production").write_text(
        "DATABASE_URL=postgresql://user:live@live.example/prod\n"
    )
    assert "localhost" in config.get_settings().database_url.get_secret_value()
    assert config.get_settings().app_env == "development"


def test_production_is_explicit(monkeypatch, clean_settings):
    (clean_settings / ".env.production").write_text(
        "DATABASE_URL=postgresql://user:live@live.example/prod\n"
    )
    monkeypatch.setenv("APP_ENV", "production")
    assert "live.example" in config.get_settings().database_url.get_secret_value()


def test_production_has_no_local_fallback(monkeypatch, clean_settings):
    (clean_settings / ".env.local").write_text("DATABASE_URL=postgresql://u:p@localhost/dev")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="Production requires DATABASE_URL"):
        config.get_settings()


def test_local_rejects_remote_environment_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@live.example/prod")
    with pytest.raises(ValueError, match="must use local PostgreSQL"):
        config.get_settings()


def test_file_cannot_switch_environment(clean_settings):
    (clean_settings / ".env.local").write_text(
        "APP_ENV=production\nDATABASE_URL=postgresql://u:p@live.example/prod"
    )
    with pytest.raises(ValueError, match="must use local PostgreSQL"):
        config.get_settings()


def test_host_query_cannot_redirect_local_connection(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/dev?host=live.example")
    with pytest.raises(ValueError, match="cannot override"):
        config.get_settings()


def test_invalid_environment_fails(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ValueError, match="APP_ENV must be"):
        config.get_settings()


def test_test_mode_does_not_read_local_file(monkeypatch, clean_settings):
    (clean_settings / ".env.local").write_text("DATABASE_URL=postgresql://u:p@localhost/dev")
    monkeypatch.setenv("APP_ENV", "test")
    assert config.get_settings().database_url.get_secret_value() == ""
