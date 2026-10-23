import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ingest.errors import SourceUnavailableError

logger = logging.getLogger(__name__)


class ApiClient:
    """Thin HTTP wrapper. All outbound calls go through here so retries, timeouts and paging are uniform."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @retry(
        retry=retry_if_exception_type(requests.ConnectionError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, max=30),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._session.get(f"{self._base_url}/{path}", params=params, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def get_pages(self, path: str, page_size: int):
        """Yield records across all pages."""
        cursor = None
        while True:
            try:
                payload = self._get(path, {"limit": page_size, "cursor": cursor})
            except requests.ConnectionError as exc:
                raise SourceUnavailableError(path) from exc
            yield from payload["records"]
            cursor = payload.get("next_cursor")
            if not cursor:
                return
