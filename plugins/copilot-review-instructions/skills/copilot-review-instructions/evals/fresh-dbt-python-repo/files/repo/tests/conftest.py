import pytest

from ingest.config import get_settings


@pytest.fixture
def settings_env(monkeypatch):
    for key, value in {"INGEST_SALESFORCE_BASE_URL": "https://sf.test", "INGEST_SALESFORCE_TOKEN": "t",
                       "INGEST_ERP_BASE_URL": "https://erp.test"}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
