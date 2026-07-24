"""Wikidata SPARQL source adapter: fetch Royal Navy sailing-ship data."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger("wikidata")

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "royal-navy-ships-dataset/0.1 (https://github.com/PeteRichardson/royal_navy_ships_dataset)"

ROYAL_NAVY_QID = "Q172771"

RATING_CLASS_QIDS: Dict[str, str] = {
    "Q892367": "First",
    "Q892368": "Second",
    "Q892492": "Third",
    "Q892562": "Fourth",
    "Q892554": "Fifth",
    "Q892278": "Sixth",
    "Q928235": "Sloop",
    "Q130396697": "Gun-brig",
}

CHUNK_SIZE = 200


def run_sparql_query(query: str, retries: int = 3, backoff_seconds: float = 2.0) -> dict:
    data = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(
        SPARQL_ENDPOINT,
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
            logger.warning("SPARQL query failed (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"SPARQL query failed after {retries} attempts") from last_error


def build_candidates_query() -> str:
    values = " ".join(f"wd:{qid}" for qid in RATING_CLASS_QIDS)
    return f"""
    SELECT ?ship ?shipLabel ?shipDescription ?class WHERE {{
      ?ship wdt:P137 wd:{ROYAL_NAVY_QID} .
      ?ship wdt:P31 ?class .
      VALUES ?class {{ {values} }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    """


def build_events_query(ship_qids: List[str]) -> str:
    values = " ".join(f"wd:{qid}" for qid in ship_qids)
    return f"""
    SELECT ?ship ?event ?eventLabel ?date ?namedAs WHERE {{
      VALUES ?ship {{ {values} }}
      ?ship p:P793 ?es .
      ?es ps:P793 ?event .
      OPTIONAL {{ ?es pq:P585 ?date . }}
      OPTIONAL {{ ?es pq:P1810 ?namedAs . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    """


def build_armament_query(ship_qids: List[str]) -> str:
    values = " ".join(f"wd:{qid}" for qid in ship_qids)
    return f"""
    SELECT ?ship ?guns WHERE {{
      VALUES ?ship {{ {values} }}
      ?ship p:P520 ?armament .
      ?armament pq:P1114 ?guns .
    }}
    """


def _chunked(items: List[str], size: int) -> Iterator[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_events(ship_qids: List[str]) -> List[dict]:
    rows: List[dict] = []
    for chunk in _chunked(ship_qids, CHUNK_SIZE):
        result = run_sparql_query(build_events_query(chunk))
        rows.extend(result["results"]["bindings"])
    return rows


def fetch_armament(ship_qids: List[str]) -> List[dict]:
    rows: List[dict] = []
    for chunk in _chunked(ship_qids, CHUNK_SIZE):
        result = run_sparql_query(build_armament_query(chunk))
        rows.extend(result["results"]["bindings"])
    return rows
