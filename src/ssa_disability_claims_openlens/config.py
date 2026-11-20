"""
Application configuration loaded from environment variables.

Uses pydantic-settings pattern with explicit os.getenv fallbacks
so the server works without installing pydantic-settings separately.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """
    All runtime configuration for the OpenLens MCP server.

    Values are read from environment variables at startup. Defaults
    are chosen so the server runs correctly without any .env file.
    """

    # ── Server identity ────────────────────────────────────────────────────────
    server_name: str = Field(default="SSA Disability Claims OpenLens")
    server_version: str = Field(default="1.0.0")
    log_level: str = Field(default="INFO")

    # ── Data source adapters ───────────────────────────────────────────────────
    ssa_open_data_base_url: str = Field(default="https://www.ssa.gov/data/")
    data_gov_api_base_url: str = Field(
        default="https://catalog.data.gov/api/3/action"
    )
    data_gov_api_key: str = Field(default="")

    @field_validator("data_gov_api_base_url")
    @classmethod
    def validate_data_gov_url(cls, v: str) -> str:
        """
        Reject any base URL that does not point to the official Data.gov CKAN API.

        This eliminates the SSRF path where a compromised environment variable
        redirects outbound requests to an internal endpoint (e.g. cloud metadata
        service at 169.254.169.254, or a private network host).

        The URL must start with 'https://catalog.data.gov/' — no other host,
        no HTTP (downgrade), no IP literals.
        """
        _ALLOWED_PREFIX = "https://catalog.data.gov/"
        if not v.startswith(_ALLOWED_PREFIX):
            raise ValueError(
                f"data_gov_api_base_url must start with '{_ALLOWED_PREFIX}'. "
                f"Got: {v!r}. Set DATA_GOV_API_BASE_URL to an allowed value "
                "or leave it unset to use the default."
            )
        return v

    # ── Cache settings ─────────────────────────────────────────────────────────
    catalog_cache_ttl_seconds: int = Field(default=3600)

    # ── Answer Coverage thresholds ─────────────────────────────────────────────
    # These map numeric scores (0–100) to CoverageRating levels
    coverage_complete_threshold: float = Field(default=90.0)
    coverage_high_threshold: float = Field(default=75.0)
    coverage_partial_threshold: float = Field(default=40.0)
    coverage_limited_threshold: float = Field(default=15.0)

    @classmethod
    def from_env(cls) -> "Settings":
        """Construct Settings from environment variables."""
        return cls(
            server_name=os.getenv(
                "OPENLENS_SERVER_NAME", "SSA Disability Claims OpenLens"
            ),
            server_version=os.getenv("OPENLENS_SERVER_VERSION", "1.0.0"),
            log_level=os.getenv("OPENLENS_LOG_LEVEL", "INFO"),
            ssa_open_data_base_url=os.getenv(
                "SSA_OPEN_DATA_BASE_URL", "https://www.ssa.gov/data/"
            ),
            data_gov_api_base_url=os.getenv(
                "DATA_GOV_API_BASE_URL", "https://catalog.data.gov/api/3/action"
            ),
            data_gov_api_key=os.getenv("DATA_GOV_API_KEY", ""),
            catalog_cache_ttl_seconds=int(
                os.getenv("CATALOG_CACHE_TTL_SECONDS", "3600")
            ),
            coverage_high_threshold=float(
                os.getenv("COVERAGE_HIGH_THRESHOLD", "75")
            ),
            coverage_partial_threshold=float(
                os.getenv("COVERAGE_PARTIAL_THRESHOLD", "40")
            ),
            coverage_limited_threshold=float(
                os.getenv("COVERAGE_LIMITED_THRESHOLD", "15")
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings.from_env()
