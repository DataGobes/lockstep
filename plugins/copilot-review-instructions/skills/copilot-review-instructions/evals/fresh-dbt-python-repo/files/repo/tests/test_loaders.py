import pytest

from ingest.errors import SchemaDriftError
from ingest.loaders import load_accounts


class FakeClient:
    def __init__(self, records):
        self._records = records

    def get_pages(self, path, page_size):
        yield from self._records


def test_load_accounts_stamps_loaded_at(settings_env):
    rows = load_accounts(FakeClient([{"Id": "1", "Name": "A", "Industry": "X", "BillingCountry": "NL",
                                       "CreatedDate": "2024-01-01", "IsDeleted": False}]))
    assert rows[0]["_loaded_at"]


def test_load_accounts_raises_on_schema_drift(settings_env):
    with pytest.raises(SchemaDriftError):
        load_accounts(FakeClient([{"Id": "1"}]))
