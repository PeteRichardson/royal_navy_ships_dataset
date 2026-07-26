"""Shared SPARQL-over-HTTP client used by every source adapter."""

import email.utils
import http.client
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Iterator, List, Optional

logger = logging.getLogger("sparql")

USER_AGENT = "royal-navy-ships-dataset/0.1 (https://github.com/PeteRichardson/royal_navy_ships_dataset)"

# Failures worth another attempt. The two non-obvious entries are the ones a
# truncated response actually raises: `IncompleteRead` subclasses
# `HTTPException` and has no relation to `URLError`, and `ConnectionResetError`
# subclasses `OSError` as a *sibling* of `URLError` rather than a descendant --
# so neither was caught, and a body cut short mid-transfer aborted the whole
# pipeline run. `socket.timeout` needs no entry: it has been an alias for
# `TimeoutError` since Python 3.10.
RETRYABLE_EXCEPTIONS = (
    urllib.error.URLError,  # includes HTTPError -- see _is_permanent
    TimeoutError,
    json.JSONDecodeError,
    http.client.IncompleteRead,
    ConnectionResetError,
)

# 4xx statuses a retry can plausibly fix. Everything else in the 4xx range is
# the client's fault and fails identically on every attempt.
RETRYABLE_CLIENT_STATUSES = frozenset({408, 429})

# Statuses on which the server is expected to say when to come back.
RETRY_AFTER_STATUSES = frozenset({429, 503})

# A server is free to ask for an hour; the pipeline is not willing to block that
# long, and an unbounded sleep read off the wire is a hang waiting to happen.
MAX_RETRY_AFTER_SECONDS = 120.0


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Seconds to wait per an HTTP `Retry-After` header, or None if unusable.

    Accepts both wire forms: delta-seconds (`"30"`) and an HTTP-date
    (`"Wed, 21 Oct 2026 07:28:00 GMT"`). The result is clamped to
    [0, MAX_RETRY_AFTER_SECONDS], so a date already in the past yields 0 rather
    than a negative sleep and an implausibly distant one is capped.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # RFC 9110 defines delta-seconds as a non-negative integer, so `isdigit` is
    # exactly the right test -- and it rejects "inf"/"nan", which float() would
    # accept and which would then survive the clamp below as a sleep forever.
    if value.isdigit():
        seconds = float(value)
    else:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - (now or datetime.now(timezone.utc))).total_seconds()
    return max(0.0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def _is_permanent(exc: BaseException) -> bool:
    """Whether retrying `exc` is pointless.

    `HTTPError` subclasses `URLError`, so before this check every HTTP status
    was retried: a malformed query returning 400 burned all three attempts and
    both backoff sleeps before failing with the error it already had.
    """
    if not isinstance(exc, urllib.error.HTTPError):
        return False
    return 400 <= exc.code < 500 and exc.code not in RETRYABLE_CLIENT_STATUSES


def _retry_after_delay(exc: BaseException) -> Optional[float]:
    """The server's requested wait for a rate-limit response, if it gave one."""
    if not isinstance(exc, urllib.error.HTTPError):
        return None
    if exc.code not in RETRY_AFTER_STATUSES:
        return None
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    return parse_retry_after(headers.get("Retry-After"))


def run_query(
    endpoint: str,
    query: str,
    retries: int = 3,
    backoff_seconds: float = 2.0,
    rate_limit_retries: int = 5,
) -> dict:
    """POST `query` to `endpoint` and return the parsed SPARQL JSON result.

    Transient failures get `retries` attempts with linear backoff. A rate-limit
    response carrying `Retry-After` is handled separately: the client waits
    exactly as long as the server asked (bounded by MAX_RETRY_AFTER_SECONDS)
    and does not spend the ordinary retry budget doing so, since a busy
    endpoint would otherwise exhaust every attempt before the query was ever
    answered. Those waits have their own cap, `rate_limit_retries`, so the loop
    still terminates against an endpoint that never lets up.
    """
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        method="POST",
    )
    last_error: Optional[Exception] = None
    attempts = 0
    rate_limit_waits = 0
    while True:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except RETRYABLE_EXCEPTIONS as exc:
            last_error = exc
            if _is_permanent(exc):
                raise RuntimeError(
                    f"SPARQL query to {endpoint} failed permanently: {exc}"
                ) from exc

            delay = _retry_after_delay(exc)
            if delay is not None:
                rate_limit_waits += 1
                if rate_limit_waits > rate_limit_retries:
                    break
                logger.warning(
                    "Rate limited by %s; honoring Retry-After: waiting %.1fs (wait %d/%d)",
                    endpoint,
                    delay,
                    rate_limit_waits,
                    rate_limit_retries,
                )
                time.sleep(delay)
                continue

            attempts += 1
            logger.warning(
                "SPARQL query to %s failed (attempt %d/%d): %s", endpoint, attempts, retries, exc
            )
            if attempts >= retries:
                break
            time.sleep(backoff_seconds * attempts)
    raise RuntimeError(
        f"SPARQL query to {endpoint} failed after {attempts} attempts "
        f"and {rate_limit_waits} rate-limit waits"
    ) from last_error


def chunked(items: List[str], size: int) -> Iterator[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
