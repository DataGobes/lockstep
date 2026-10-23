import logging
from datetime import datetime, timezone

from ingest.client import ApiClient
from ingest.config import get_settings
from ingest.errors import SchemaDriftError

logger = logging.getLogger(__name__)

EXPECTED_ACCOUNT_FIELDS = {"Id", "Name", "Industry", "BillingCountry", "CreatedDate", "IsDeleted"}


def load_accounts(client: ApiClient) -> list[dict]:
    """Fetch Salesforce accounts and stamp them with a load timestamp."""
    settings = get_settings()
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for record in client.get_pages("sobjects/Account", settings.page_size):
        missing = EXPECTED_ACCOUNT_FIELDS - record.keys()
        if missing:
            raise SchemaDriftError(f"Account payload missing {sorted(missing)}")
        rows.append({**record, "_loaded_at": loaded_at})
    logger.info("Loaded %d accounts", len(rows))
    return rows
