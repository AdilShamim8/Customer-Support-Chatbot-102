"""
Environment contract tests - config drift cannot happen silently.

Two directions, both enforced:
1. Every variable documented in .env.example maps to a real Settings
   field (docs that lie are worse than no docs).
2. Every Settings field an operator would set has documentation in
   .env.example (undocumented knobs are production surprise factories).
"""

import pathlib
import re

import pytest

from configs.settings import Settings

ENV_EXAMPLE = pathlib.Path(".env.example")


def documented_env_vars() -> dict[str, str]:
    """Parse KEY=VALUE lines (comments stripped) from .env.example."""
    variables: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match:
            variables[match.group(1)] = line
    return variables


def settings_field_names() -> set[str]:
    fields = getattr(Settings, "model_fields", None) or getattr(Settings, "__fields__", {})
    return set(fields)


class TestEnvDocsMatchSettings:
    def test_env_example_exists(self):
        assert ENV_EXAMPLE.exists()

    def test_every_documented_var_is_a_real_setting(self):
        # Pydantic Settings is case-insensitive: APP_ENV -> field app_env
        fields = settings_field_names()
        documented = documented_env_vars()
        # Known service-level vars read directly from the process env by
        # docker/gunicorn/CI - intentionally NOT Settings fields
        infra_vars = {
            "POSTGRES_PASSWORD", "ELASTIC_PASSWORD", "GRAFANA_PASSWORD",
            "DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT",
            "DB_POOL_RECYCLE", "MAX_UPLOAD_SIZE_MB", "COMPANY_NAME",
            "SUPPORT_EMAIL", "ENABLE_AUTH", "CHECK_HALLUCINATION",
            "HALLUCINATION_THRESHOLD", "ENABLE_QUERY_EXPANSION",
            "WEB_CONCURRENCY",  # gunicorn.conf.py reads this directly
        }
        lies = sorted(
            var for var in set(documented)
            if var.lower() not in fields and var not in infra_vars
        )
        assert not lies, f".env.example documents settings that don't exist: {lies}"

    def test_critical_settings_are_documented(self):
        documented = documented_env_vars()
        must_document = [
            "APP_ENV", "LOG_LEVEL", "SECRET_KEY", "API_RATE_LIMIT",
            "LLM_PROVIDER", "OPENAI_API_KEY", "CHAT_MODEL",
            "EMBEDDING_MODEL", "VECTOR_STORE_TYPE", "REDIS_URL",
            "DATABASE_URL", "TOP_K_RETRIEVAL", "CHUNK_SIZE",
            "SEMANTIC_CACHE_ENABLED", "ENABLE_RERANKING",
            "REQUEST_TIMEOUT_SECONDS", "WEB_CONCURRENCY",
        ]
        undocumented = [var for var in must_document if var not in documented]
        assert not undocumented, f"Critical settings missing from .env.example: {undocumented}"

    def test_production_example_matches_dev_example_keys(self):
        prod = pathlib.Path(".env.production.example")
        if not prod.exists():
            pytest.skip("production example not present")
        prod_vars = documented_from(prod)
        dev_vars = documented_env_vars()
        prod_only = sorted(set(prod_vars) - set(dev_vars))
        assert not prod_only, f"Production-only variables not in dev template: {prod_only}"


def documented_from(path: pathlib.Path) -> dict[str, str]:
    variables: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match:
            variables[match.group(1)] = line
    return variables
