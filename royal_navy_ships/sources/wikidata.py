"""Wikidata SPARQL source adapter: fetch Royal Navy sailing-ship data."""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from royal_navy_ships.model import Ship, ShipEvent, ShipName, new_ship_id

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

CACHE_PATH = Path(".cache/wikidata_raw.json")


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


def _qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def parse_candidates(rows: List[dict]) -> Dict[str, dict]:
    ships: Dict[str, dict] = {}
    for row in rows:
        qid = _qid_from_uri(row["ship"]["value"])
        if qid in ships:
            continue  # ship matched more than one rating class; first match wins
        class_qid = _qid_from_uri(row["class"]["value"])
        ships[qid] = {
            "label": row.get("shipLabel", {}).get("value", qid),
            "description": row.get("shipDescription", {}).get("value", ""),
            "rating": RATING_CLASS_QIDS.get(class_qid),
            "events": [],
            "guns_counts": [],
        }
    return ships


def attach_events(ships: Dict[str, dict], rows: List[dict]) -> None:
    for row in rows:
        qid = _qid_from_uri(row["ship"]["value"])
        if qid not in ships:
            continue
        ships[qid]["events"].append(
            ShipEvent(
                description=row.get("eventLabel", {}).get("value", ""),
                date=row.get("date", {}).get("value"),
                named_as=row.get("namedAs", {}).get("value"),
            )
        )


def attach_armament(ships: Dict[str, dict], rows: List[dict]) -> None:
    for row in rows:
        qid = _qid_from_uri(row["ship"]["value"])
        if qid not in ships:
            continue
        ships[qid]["guns_counts"].append(int(row["guns"]["value"]))


def build_names(label: str, events: List[ShipEvent]) -> List[ShipName]:
    named_events = sorted(
        (e for e in events if e.named_as and e.date),
        key=lambda e: e.date,
    )
    if not named_events:
        return [ShipName(name=label)]

    names: List[ShipName] = []
    for i, event in enumerate(named_events):
        end_date = named_events[i + 1].date if i + 1 < len(named_events) else None
        names.append(ShipName(name=event.named_as, start_date=event.date, end_date=end_date))
    return names


def to_ships(ships: Dict[str, dict]) -> List[Ship]:
    result = []
    for qid, data in ships.items():
        # Wikidata's armament data (P520/P1114) is very sparse and, where present,
        # was found during design to sometimes undercount well-documented ships
        # (e.g. HMS Victory) -- treat this sum as best-effort, not authoritative.
        guns = str(sum(data["guns_counts"])) if data["guns_counts"] else None
        result.append(
            Ship(
                id=new_ship_id(),
                names=build_names(data["label"], data["events"]),
                guns=guns,
                rating=data["rating"],
                notes=data["description"],
                events=data["events"],
                external_ids={"wikidata": qid},
            )
        )
    return result


def load_cache(cache_path: Path) -> Optional[dict]:
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("cache file %s is unreadable or corrupt; ignoring it", cache_path)
        return None


def save_cache(cache_path: Path, raw: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, sort_keys=True)
    os.replace(tmp_path, cache_path)


def _canonicalize(raw: dict) -> dict:
    """Sort each query's binding rows into a stable order so that comparing
    two raw results is insensitive to Wikidata's nondeterministic row order."""
    return {
        key: sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
        for key, rows in raw.items()
    }


def fetch_ships(cache_path: Path = CACHE_PATH) -> Tuple[List[Ship], bool]:
    """Fetch ships from Wikidata. Returns (ships, changed) -- changed is False
    if the freshly-fetched raw result is identical to what's cached on disk."""
    candidates_result = run_sparql_query(build_candidates_query())
    candidate_rows = candidates_result["results"]["bindings"]
    ship_qids = sorted({_qid_from_uri(row["ship"]["value"]) for row in candidate_rows})

    raw = _canonicalize({
        "candidates": candidate_rows,
        "events": fetch_events(ship_qids),
        "armament": fetch_armament(ship_qids),
    })

    cached = load_cache(cache_path)
    changed = raw != cached
    if changed:
        save_cache(cache_path, raw)

    ships = parse_candidates(raw["candidates"])
    attach_events(ships, raw["events"])
    attach_armament(ships, raw["armament"])
    return to_ships(ships), changed
