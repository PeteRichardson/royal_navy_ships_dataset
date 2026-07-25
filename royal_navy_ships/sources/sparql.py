"""Shared SPARQL-over-HTTP client used by every source adapter."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator, List, Optional

logger = logging.getLogger("sparql")

USER_AGENT = "royal-navy-ships-dataset/0.1 (https://github.com/PeteRichardson/royal_navy_ships_dataset)"


def run_query(endpoint: str, query: str, retries: int = 3, backoff_seconds: float = 2.0) -> dict:
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        method="POST",
    )
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            logger.warning(
                "SPARQL query to %s failed (attempt %d/%d): %s", endpoint, attempt, retries, exc
            )
            if attempt < retries:
                time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"SPARQL query to {endpoint} failed after {retries} attempts") from last_error


def chunked(items: List[str], size: int) -> Iterator[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
