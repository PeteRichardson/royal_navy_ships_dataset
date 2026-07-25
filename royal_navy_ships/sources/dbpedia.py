"""DBpedia source adapter: enrich canonical ships with Wikipedia infobox data.

DBpedia mirrors English Wikipedia's ship infoboxes, which carry the armament,
tonnage, dimensions and crew figures that Wikidata almost always lacks. Ships
are joined on the Wikidata QID each record already holds, via DBpedia's own
`owl:sameAs` links -- no name matching, and specifically not the old
lookup.dbpedia.org keyword search, which returns the wrong century's ship for
reused names (searching "HMS Bellerophon" surfaces the 1907 dreadnought).
"""

import logging
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from royal_navy_ships import cache
from royal_navy_ships.model import Ship
from royal_navy_ships.sources import sparql

logger = logging.getLogger("dbpedia")

SPARQL_ENDPOINT = "https://dbpedia.org/sparql"
CACHE_PATH = Path(".cache/dbpedia_raw.json")

# The public endpoint caps result rows (~10k). At roughly 11 rows per ship,
# 200 ships per request stays far under that.
CHUNK_SIZE = 200

DBO = "http://dbpedia.org/ontology/"
DBP = "http://dbpedia.org/property/"
RESOURCE_PREFIX = "http://dbpedia.org/resource/"

# Canonical field -> DBpedia properties in preference order. `dbo:` (ontology)
# properties are typed and already normalized, so they are preferred where they
# exist; `dbp:` properties are raw infobox fragments and need cleaning.
#
# There is deliberately no draught entry: dbp:shipDraught, dbp:shipDraft and
# dbo:draft all returned zero rows when this adapter was designed.
FIELD_PROPERTIES: Dict[str, Tuple[str, ...]] = {
    "armament": (DBP + "shipArmament",),
    "tonnage": (DBP + "shipTonsBurthen", DBP + "shipDisplacement"),
    "length": (DBO + "length", DBP + "shipLength"),
    "beam": (DBO + "shipBeam",),
    "complement": (DBP + "shipComplement",),
    "sail_plan": (DBP + "shipSailPlan",),
    "builder": (DBP + "shipBuilder", DBO + "builder"),
    "fate": (DBP + "shipFate",),
}

QUERIED_PROPERTIES: Tuple[str, ...] = tuple(
    sorted({prop for props in FIELD_PROPERTIES.values() for prop in props})
)


def build_properties_query(ship_qids: List[str]) -> str:
    """One row per (ship, property, value).

    The property list is a VALUES block rather than one OPTIONAL per property
    on purpose: independent OPTIONAL blocks cross-product their rows for any
    ship with several multi-valued properties.
    """
    values = " ".join(f"<http://www.wikidata.org/entity/{qid}>" for qid in ship_qids)
    props = " ".join(f"<{prop}>" for prop in QUERIED_PROPERTIES)
    return f"""
    SELECT ?wd ?resource ?p ?o WHERE {{
      VALUES ?wd {{ {values} }}
      ?resource owl:sameAs ?wd .
      VALUES ?p {{ {props} }}
      ?resource ?p ?o .
    }}
    """


def fetch_rows(ship_qids: List[str]) -> List[dict]:
    rows: List[dict] = []
    for chunk in sparql.chunked(ship_qids, CHUNK_SIZE):
        result = sparql.run_query(SPARQL_ENDPOINT, build_properties_query(chunk))
        rows.extend(result["results"]["bindings"])
    return rows


WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
BULLET_RE = re.compile(r"(?m)^[*:#]+\s*")
WHITESPACE_RE = re.compile(r"\s+")
SEPARATOR_RE = re.compile(r"(;\s*)+")
ALNUM_RE = re.compile(r"[A-Za-z0-9]")

# Wikipedia's ship infoboxes routinely emit a bare "--MM-DD" fragment where a
# fate date failed to render; roughly two thirds of observed dbp:shipFate values
# look like this. They carry no information and must not reach a canonical field.
JUNK_DATE_RE = re.compile(r"^-{2}\d{2}-\d{2}$")

PLAIN_INT_RE = re.compile(r"^\d{1,3}$")
STATED_TOTAL_RE = re.compile(r"^(\d{1,3})\s+guns?\b", re.IGNORECASE)


def label_from_resource_uri(uri: str) -> str:
    """`.../resource/Full-rigged_ship` -> `Full-rigged ship`."""
    return urllib.parse.unquote(uri[len(RESOURCE_PREFIX) :]).replace("_", " ")


def clean_value(value: str) -> Optional[str]:
    """Normalize one raw DBpedia value, or return None if it is unusable.

    Values arrive in three shapes: clean literals, DBpedia resource URIs (most
    sail plans and builders), and multi-line infobox wikitext. Anything that
    cleans down to punctuation, emptiness, or a malformed date fragment is
    dropped rather than stored -- a canonical field should never hold junk.
    """
    if value.startswith(RESOURCE_PREFIX):
        text = label_from_resource_uri(value)
    else:
        text = value
        for _ in range(5):
            stripped = TEMPLATE_RE.sub(" ", text)
            if stripped == text:
                break
            text = stripped
        text = WIKILINK_RE.sub(lambda match: match.group(1), text)
        text = BULLET_RE.sub("", text)
        text = text.replace("\n", "; ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    text = SEPARATOR_RE.sub("; ", text).strip("; ").strip()
    if (
        not text
        or not ALNUM_RE.search(text)
        or JUNK_DATE_RE.match(text)
        or any(marker in text for marker in ("{{", "}}", "[[", "]]"))
    ):
        return None
    return text


def extract_gun_count(armament: str) -> Optional[str]:
    """Pull a total gun count out of a cleaned armament string, if one is stated.

    Accepts only a bare integer or an explicitly stated total ("28 guns
    comprising: ..."). Summing the per-deck "24 x 9-pounder" multipliers is
    deliberately not attempted: many entries cover several eras or navies
    ("As built: ... From 1780: ...", "Royal Navy ... Citoyen ..."), so a naive
    sum would silently double-count. Expect a total for roughly half of
    matched ships; the full text is always kept in `armament` regardless.
    """
    if PLAIN_INT_RE.match(armament):
        return armament
    match = STATED_TOTAL_RE.match(armament)
    return match.group(1) if match else None


def _qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _resource_name(uri: str) -> str:
    return uri[len(RESOURCE_PREFIX) :] if uri.startswith(RESOURCE_PREFIX) else uri


def index_rows(rows: List[dict]) -> Dict[str, dict]:
    """Group raw rows by ship QID.

    Returns qid -> {"resource": <resource uri>, "properties": {prop: [values]}},
    where each value list is cleaned, deduplicated and sorted for determinism.
    """
    indexed: Dict[str, dict] = {}
    for row in rows:
        qid = _qid_from_uri(row["wd"]["value"])
        entry = indexed.setdefault(
            qid, {"resource": row["resource"]["value"], "properties": {}}
        )
        cleaned = clean_value(row["o"]["value"])
        if cleaned is None:
            continue
        values = entry["properties"].setdefault(row["p"]["value"], [])
        if cleaned not in values:
            values.append(cleaned)
    for entry in indexed.values():
        for values in entry["properties"].values():
            values.sort()
    return indexed


def enrich(ships: List[Ship], indexed: Dict[str, dict]) -> int:
    """Merge DBpedia values into `ships` in place; returns how many were enriched.

    Where DBpedia offers several values for one field (a handful of ships list
    more than one builder or fate), the first in sorted order becomes the
    canonical answer and the rest are recorded through the same conflict
    mechanism used across sources -- so nothing is silently discarded.
    """
    enriched = 0
    for ship in ships:
        qid = ship.external_ids.get("wikidata")
        entry = indexed.get(qid) if qid else None
        if entry is None:
            continue
        ship.external_ids["dbpedia"] = _resource_name(entry["resource"])
        for field_name, props in FIELD_PROPERTIES.items():
            for prop in props:
                values = entry["properties"].get(prop)
                if not values:
                    continue
                for value in values:
                    ship.set_field(field_name, value, "dbpedia")
                break
        if ship.armament:
            ship.set_field("guns", extract_gun_count(ship.armament), "dbpedia")
        enriched += 1
    return enriched


def fetch_enrichment(
    ships: List[Ship], cache_path: Path = CACHE_PATH
) -> Tuple[bool, dict]:
    """Enrich `ships` in place from DBpedia. Returns (changed, raw).

    `changed` is False when the freshly-fetched result matches the cache; `raw`
    is the canonicalized result the caller should persist once it has committed
    its own output. Like the Wikidata adapter, this never writes the cache
    itself. Ships with no DBpedia resource -- about a quarter of the fleet,
    mostly vessels with no English Wikipedia article -- are simply left as-is.
    """
    ship_qids = sorted(
        {
            ship.external_ids["wikidata"]
            for ship in ships
            if "wikidata" in ship.external_ids
        }
    )
    raw = cache.canonicalize({"properties": fetch_rows(ship_qids)})
    changed = raw != cache.load(cache_path)

    enriched = enrich(ships, index_rows(raw["properties"]))
    logger.info("Enriched %d of %d ships from DBpedia", enriched, len(ships))
    return changed, raw
