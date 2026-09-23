import pytest

from apps.api import config

META_NAMES = (
    "META_AD_ACCOUNT_ID",
    "META_ACCESS_TOKEN",
    "META_GRAPH_API_VERSION",
    "META_SYNC_START_DATE",
    "META_SYNC_LOOKBACK_DAYS",
    "META_ATTRIBUTION_WINDOWS",
    "META_ACTION_REPORT_TIME",
)


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch, tmp_path):
    for name in ("APP_ENV", "DATABASE_URL", "CORS_ORIGINS", *META_NAMES):
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


def test_blank_meta_values_do_not_block_startup(clean_settings):
    (clean_settings / ".env.local").write_text(
        "DATABASE_URL=postgresql://u:p@localhost/dev\n"
        + "".join(f"{name}=\n" for name in META_NAMES)
    )
    settings = config.get_settings()
    assert settings.meta_configured is False
    assert settings.meta_sync_start_date is None
    assert settings.meta_sync_lookback_days == 7
    assert settings.meta_attribution_windows == ["1d_view", "7d_click"]
    assert settings.meta_action_report_time == "conversion"


def test_meta_settings_parse_and_stay_secret(monkeypatch):
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_1234567890")
    monkeypatch.setenv("META_ACCESS_TOKEN", "fixture-secret-token")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v23.0")
    monkeypatch.setenv("META_SYNC_START_DATE", "2026-01-01")
    monkeypatch.setenv("META_ATTRIBUTION_WINDOWS", '["7d_click"]')
    settings = config.get_settings()
    assert settings.meta_configured is True
    assert settings.meta_ad_account_id == "1234567890"
    assert "fixture-secret-token" not in repr(settings)
    assert "fixture-secret-token" not in str(settings.model_dump())


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("META_AD_ACCOUNT_ID", "act_12;DROP"),
        ("META_GRAPH_API_VERSION", "latest"),
        ("META_ATTRIBUTION_WINDOWS", '["30d_click"]'),
        ("META_SYNC_LOOKBACK_DAYS", "0"),
        ("META_ACTION_REPORT_TIME", "whenever"),
    ],
)
def test_malformed_meta_settings_fail(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        config.get_settings()


@pytest.mark.parametrize(
    "value", ['["7d_click","1d_view"]', "[7d_click,1d_view]", "7d_click, 1d_view"]
)
def test_attribution_windows_accept_common_env_spellings(monkeypatch, value):
    monkeypatch.setenv("META_ATTRIBUTION_WINDOWS", value)
    assert config.get_settings().meta_attribution_windows == ["1d_view", "7d_click"]
