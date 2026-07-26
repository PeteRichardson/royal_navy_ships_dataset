"""Tests for the shared SPARQL client's retry policy.

Every test here patches `urlopen` and `time.sleep`; nothing touches the network
and nothing actually waits.
"""

import http.client
import json
import logging
import unittest
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock

from royal_navy_ships.sources import sparql

ENDPOINT = "https://example.invalid/sparql"
PAYLOAD = {"results": {"bindings": [{"ship": {"value": "Q1"}}]}}


def setUpModule():
    """Every test here provokes the warnings the client is supposed to log;
    printing them all would bury the actual test results."""
    logging.getLogger("sparql").setLevel(logging.CRITICAL)


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def ok():
    return FakeResponse(json.dumps(PAYLOAD).encode("utf-8"))


def http_error(code, retry_after=None):
    headers = http.client.HTTPMessage()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(ENDPOINT, code, "boom", headers, None)


@contextmanager
def responses(*outcomes):
    """Patch urlopen to yield `outcomes` in order -- exceptions are raised,
    callables are called, anything else is returned. The last outcome repeats
    forever, so a test can assert that a loop terminates. Yields
    (urlopen_mock, recorded_sleeps)."""
    sleeps = []
    calls = {"n": 0}

    def urlopen(*_args, **_kwargs):
        index = calls["n"]
        calls["n"] += 1
        outcome = outcomes[index] if index < len(outcomes) else outcomes[-1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome() if callable(outcome) else outcome

    with mock.patch("urllib.request.urlopen", side_effect=urlopen) as m:
        with mock.patch.object(sparql.time, "sleep", side_effect=sleeps.append):
            yield m, sleeps


class RetriedExceptionsTest(unittest.TestCase):
    """#11: two failure modes the retry loop exists to absorb escaped it.
    `IncompleteRead` subclasses `HTTPException`, unrelated to `URLError`;
    `ConnectionResetError` subclasses `OSError` as a *sibling* of `URLError`."""

    def assert_retried(self, exc):
        with responses(exc, ok) as (urlopen, sleeps):
            result = sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(result, PAYLOAD)
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(sleeps, [2.0])

    def test_incomplete_read_is_retried(self):
        self.assert_retried(http.client.IncompleteRead(partial=b'{"resul'))

    def test_connection_reset_is_retried(self):
        self.assert_retried(ConnectionResetError(54, "Connection reset by peer"))

    def test_url_error_is_still_retried(self):
        self.assert_retried(urllib.error.URLError("unreachable"))

    def test_timeout_is_still_retried(self):
        self.assert_retried(TimeoutError("timed out"))

    def test_invalid_json_is_still_retried(self):
        self.assert_retried(json.JSONDecodeError("bad", "doc", 0))

    def test_a_non_retryable_exception_still_propagates(self):
        with responses(ValueError("programming error")):
            with self.assertRaises(ValueError):
                sparql.run_query(ENDPOINT, "SELECT *")


class RetryBudgetTest(unittest.TestCase):
    def test_success_on_the_first_attempt_does_not_sleep(self):
        with responses(ok) as (urlopen, sleeps):
            result = sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(result, PAYLOAD)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(sleeps, [])

    def test_ordinary_failures_keep_the_three_attempt_linear_backoff(self):
        with responses(urllib.error.URLError("nope")) as (urlopen, sleeps):
            with self.assertRaises(RuntimeError):
                sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_the_original_error_is_chained(self):
        original = urllib.error.URLError("nope")
        with responses(original):
            with self.assertRaises(RuntimeError) as caught:
                sparql.run_query(ENDPOINT, "SELECT *")

        self.assertIs(caught.exception.__cause__, original)


class PermanentFailureTest(unittest.TestCase):
    """`HTTPError` subclasses `URLError`, so every HTTP status was retried --
    a malformed query returning 400 burned all three attempts and both sleeps
    before failing with the error it already had."""

    def test_a_400_fails_immediately(self):
        with responses(http_error(400)) as (urlopen, sleeps):
            with self.assertRaises(RuntimeError):
                sparql.run_query(ENDPOINT, "SELECT bad syntax")

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(sleeps, [])

    def test_a_404_fails_immediately(self):
        with responses(http_error(404)) as (urlopen, sleeps):
            with self.assertRaises(RuntimeError):
                sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(urlopen.call_count, 1)

    def test_a_500_is_still_retried(self):
        with responses(http_error(500), ok) as (urlopen, _sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(urlopen.call_count, 2)

    def test_a_408_is_still_retried(self):
        with responses(http_error(408), ok) as (urlopen, _sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(urlopen.call_count, 2)


class RetryAfterTest(unittest.TestCase):
    """#15: WDQS sends `Retry-After` on 429. Ignoring it risks the User-Agent
    being banned once the pipeline runs unattended."""

    def test_delta_seconds_is_honored(self):
        with responses(http_error(429, "30"), ok) as (urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(sleeps, [30.0])

    def test_503_retry_after_is_honored(self):
        with responses(http_error(503, "15"), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(sleeps, [15.0])

    def test_http_date_form_is_honored(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=45)
        header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")

        with responses(http_error(429, header), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 45.0, delta=2.0)

    def test_the_wait_is_bounded(self):
        with responses(http_error(429, "99999"), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(sleeps, [sparql.MAX_RETRY_AFTER_SECONDS])

    def test_a_date_in_the_past_waits_no_time(self):
        when = datetime.now(timezone.utc) - timedelta(seconds=60)
        header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")

        with responses(http_error(429, header), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(sleeps, [0.0])

    def test_an_unparseable_header_falls_back_to_ordinary_backoff(self):
        with responses(http_error(429, "soon please"), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(sleeps, [2.0])

    def test_a_429_without_the_header_falls_back_to_ordinary_backoff(self):
        with responses(http_error(429), ok) as (_urlopen, sleeps):
            sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(sleeps, [2.0])

    def test_rate_limit_waits_do_not_consume_the_ordinary_retry_budget(self):
        """Three 429s would exhaust `retries=3` if they counted against it,
        and the query would fail without ever having been answered."""
        with responses(
            http_error(429, "5"),
            http_error(429, "5"),
            http_error(429, "5"),
            ok,
        ) as (urlopen, sleeps):
            result = sparql.run_query(ENDPOINT, "SELECT *")

        self.assertEqual(result, PAYLOAD)
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleeps, [5.0, 5.0, 5.0])

    def test_relentless_rate_limiting_still_terminates(self):
        with responses(http_error(429, "5")) as (urlopen, sleeps):
            with self.assertRaises(RuntimeError):
                sparql.run_query(ENDPOINT, "SELECT *", rate_limit_retries=4)

        self.assertEqual(urlopen.call_count, 5)
        self.assertEqual(sleeps, [5.0] * 4)


class ParseRetryAfterTest(unittest.TestCase):
    def test_none_and_blank_are_unusable(self):
        self.assertIsNone(sparql.parse_retry_after(None))
        self.assertIsNone(sparql.parse_retry_after(""))
        self.assertIsNone(sparql.parse_retry_after("   "))

    def test_non_integer_delta_is_unusable(self):
        self.assertIsNone(sparql.parse_retry_after("12.5"))
        self.assertIsNone(sparql.parse_retry_after("-5"))
        self.assertIsNone(sparql.parse_retry_after("inf"))
        self.assertIsNone(sparql.parse_retry_after("nan"))

    def test_integer_delta_is_seconds(self):
        self.assertEqual(sparql.parse_retry_after("0"), 0.0)
        self.assertEqual(sparql.parse_retry_after(" 42 "), 42.0)


if __name__ == "__main__":
    unittest.main()
