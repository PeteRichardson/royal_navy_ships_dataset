"""DBpedia source adapter: enrich canonical ships with Wikipedia infobox data.

DBpedia mirrors English Wikipedia's ship infoboxes, which carry the armament,
tonnage, dimensions and crew figures that Wikidata almost always lacks. Ships
are joined on the Wikidata QID each record already holds, via DBpedia's own
`owl:sameAs` links -- no name matching, and specifically not the old
lookup.dbpedia.org keyword search, which returns the wrong century's ship for
reused names (searching "HMS Bellerophon" surfaces the 1907 dreadnought).
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple

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
