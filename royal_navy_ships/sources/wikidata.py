"""Wikidata SPARQL source adapter: fetch Royal Navy sailing-ship data."""

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from royal_navy_ships import cache
from royal_navy_ships.model import Ship, ShipEvent, ShipName, new_ship_id
from royal_navy_ships.sources import sparql

logger = logging.getLogger("wikidata")

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

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


def fetch_events(ship_qids: List[str]) -> List[dict]:
    rows: List[dict] = []
    for chunk in sparql.chunked(ship_qids, CHUNK_SIZE):
        result = sparql.run_query(SPARQL_ENDPOINT, build_events_query(chunk))
        rows.extend(result["results"]["bindings"])
    return rows


def fetch_armament(ship_qids: List[str]) -> List[dict]:
    rows: List[dict] = []
    for chunk in sparql.chunked(ship_qids, CHUNK_SIZE):
        result = sparql.run_query(SPARQL_ENDPOINT, build_armament_query(chunk))
        rows.extend(result["results"]["bindings"])
    return rows


def _qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def parse_candidates(rows: List[dict]) -> Dict[str, dict]:
    ships: Dict[str, dict] = {}
    for row in rows:
        qid = _qid_from_uri(row["ship"]["value"])
        if qid in ships:
            # ship matched more than one rating class; rows arrive canonicalized (sorted
            # by row JSON), so the pick is deterministic but has no historical meaning --
            # revisit if rating priority matters
            continue
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
        ship = Ship(
            id=new_ship_id(),
            names=build_names(data["label"], data["events"]),
            events=data["events"],
            external_ids={"wikidata": qid},
        )
        ship.set_field("guns", guns, "wikidata")
        ship.set_field("rating", data["rating"], "wikidata")
        ship.set_field("notes", data["description"], "wikidata")
        result.append(ship)
    return result


def fetch_ships(cache_path: Path = CACHE_PATH) -> Tuple[List[Ship], bool, dict]:
    """Fetch ships from Wikidata. Returns (ships, changed, raw) -- changed is False
    if the freshly-fetched raw result is identical to what's cached on disk, and raw
    is the canonicalized SPARQL result the caller should persist to the cache file
    (see the module-level cache helper) once it has successfully committed the
    corresponding output. This function does not touch the cache file itself, so a
    caller that dies before committing its output won't leave a cache that falsely
    claims the output is current."""
    candidates_result = sparql.run_query(SPARQL_ENDPOINT, build_candidates_query())
    candidate_rows = candidates_result["results"]["bindings"]
    ship_qids = sorted({_qid_from_uri(row["ship"]["value"]) for row in candidate_rows})

    raw = cache.canonicalize({
        "candidates": candidate_rows,
        "events": fetch_events(ship_qids),
        "armament": fetch_armament(ship_qids),
    })

    cached = cache.load(cache_path)
    changed = raw != cached

    ships = parse_candidates(raw["candidates"])
    attach_events(ships, raw["events"])
    attach_armament(ships, raw["armament"])
    return to_ships(ships), changed, raw
