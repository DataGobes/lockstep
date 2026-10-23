from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from env vars prefixed INGEST_ or Key Vault-backed pipeline variables."""

    model_config = SettingsConfigDict(env_prefix="INGEST_")

    salesforce_base_url: str
    salesforce_token: str
    erp_base_url: str
    landing_container: str = "raw"
    page_size: int = 2000


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings. Use this instead of reading os.environ."""
    return Settings()
