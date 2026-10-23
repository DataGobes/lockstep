import logging

from ingest.client import ApiClient
from ingest.config import get_settings
from ingest.loaders import load_accounts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def main() -> None:
    """Entry point for `python -m ingest`."""
    settings = get_settings()
    client = ApiClient(settings.salesforce_base_url, settings.salesforce_token)
    load_accounts(client)


if __name__ == "__main__":
    main()
