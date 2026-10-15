"""
Unit tests for configuration (configs/settings.py).

Contract under test: the settings layer is the single place env vars
become typed values, production/dev predicates work, and the CORS
allow-list follows the security policy (never wildcard in production).
"""

from configs.settings import Environment, Settings


class TestEnvironmentPredicates:
    def test_production_flag(self):
        s = Settings(_env_file=None, app_env="production")
        assert s.is_production is True
        assert s.is_development is False

    def test_development_flag(self):
        s = Settings(_env_file=None, app_env="development")
        assert s.is_development is True
        assert s.is_production is False

    def test_invalid_env_rejected(self):
        # A typo in APP_ENV must fail at boot, not at 3am in prod
        import pytest

        with pytest.raises(Exception):
            Settings(_env_file=None, app_env="produciton")


class TestCorsPolicy:
    def test_production_never_wildcard(self):
        s = Settings(_env_file=None, app_env="production")
        assert "*" not in s.cors_origin_list

    def test_development_defaults_wildcard(self):
        s = Settings(_env_file=None, app_env="development")
        assert "*" in s.cors_origin_list

    def test_explicit_list_parsed_and_trimmed(self):
        s = Settings(
            _env_file=None,
            app_env="production",
            cors_origins="https://a.com, https://b.com ,",
        )
        assert s.cors_origin_list == ["https://a.com", "https://b.com"]


class TestProductionHardeningDefaults:
    """Defaults added 2026-10-15 - each guards a documented failure mode."""

    def test_timeout_defaults_exist(self):
        s = Settings(_env_file=None, app_env="test")
        assert s.request_timeout_seconds == 30.0
        assert s.stream_first_token_timeout_seconds == 10.0

    def test_circuit_breaker_defaults(self):
        s = Settings(_env_file=None, app_env="test")
        assert s.circuit_breaker_failure_threshold == 5
        assert s.circuit_breaker_reset_seconds == 30

    def test_semantic_cache_off_by_default(self):
        # Off until explicitly enabled: cost-feature, opt-in
        s = Settings(_env_file=None, app_env="test")
        assert s.semantic_cache_enabled is False

    def test_fallback_message_is_user_friendly(self):
        # The F1 degraded mode copy - must exist and must not leak internals
        s = Settings(_env_file=None, app_env="test")
        assert "human" in s.fallback_message.lower()

    def test_env_override_reaches_settings(self, monkeypatch):
        monkeypatch.setenv("API_RATE_LIMIT", "7")
        s = Settings(_env_file=None)
        assert s.api_rate_limit == 7


class TestCachedAccessor:
    def test_get_settings_is_cached(self):
        from configs.settings import get_settings

        assert get_settings() is get_settings()
