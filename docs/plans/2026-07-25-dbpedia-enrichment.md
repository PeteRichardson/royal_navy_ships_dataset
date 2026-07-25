# DBpedia Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the canonical ship dataset with DBpedia (Wikipedia infobox) data — armament, tonnage, dimensions, complement, sail plan, builder, fate — joined deterministically on the Wikidata QIDs each ship already carries, with per-field provenance and conflict capture (implements GitHub issue #4 per `docs/specs/2026-07-25-dbpedia-enrichment-design.md`).

**Architecture:** Two shared modules are extracted first (`sources/sparql.py` for SPARQL-over-HTTP, `cache.py` for raw-result caching) so the new adapter doesn't have to import from `wikidata.py`. `model.py` gains descriptive fields plus a `set_field(name, value, source)` merge method that implements the project's data-first conflict policy: the first source to supply a value owns the canonical answer, later disagreeing values are preserved in `conflicts` rather than overwriting or being dropped. `sources/dbpedia.py` then batch-joins DBpedia resources to ship QIDs via `owl:sameAs`, cleans the notoriously messy infobox values, and merges them through `set_field`.

**Tech Stack:** Python 3 standard library only (`argparse`, `dataclasses`, `json`, `logging`, `os`, `pathlib`, `re`, `time`, `urllib`, `uuid`).

## Global Constraints

- **Python 3 standard library only.** No third-party dependencies (no `requests`, no `aiohttp`, no `SPARQLWrapper`); neither is installed in this environment and there is no `requirements.txt`.
- **`ships.json` and everything under `.cache/` are gitignored and must never be committed.** The dataset is published via GitHub Releases.
- **Transactional ordering must be preserved** (established in PR #10): adapters never write their own cache. `ships.json` is written atomically (tmp + `os.replace`), and caches are committed only *after* that write succeeds. A run killed mid-write must never leave a cache claiming the output is current.
- **No AI/LLM parsing in this issue** — deterministic string cleaning only.
- **Precedence:** Wikidata wins where it has a value; DBpedia fills gaps. A lone source's value wins by default.
- **No test framework exists in this repo.** Verification steps below are runnable `python3 -c` snippets with real assertions; several hit the live DBpedia/Wikidata endpoints, which is intentional and required (hand-verification against live endpoints is what caught the query-shape bugs recorded below). `clean_value` and `extract_gun_count` are pure functions and would be the natural first candidates if a suite is ever added — do not add one here.

### Verified facts this plan depends on

All checked live against `https://dbpedia.org/sparql` on 2026-07-25, using a 60-ship sample drawn from the pipeline's own Wikidata filter.

- **The QID join works and is 1:1.** `?resource owl:sameAs <http://www.wikidata.org/entity/QID>` resolves correctly (Q213958 → `dbr:HMS_Victory`, Q5634103 → `dbr:HMS_Rose_(1757)`). Across 60 sampled ships, **zero** QIDs mapped to more than one DBpedia resource.
- **Long-format property query avoids the cross-product bug.** Selecting `?wd ?resource ?p ?o` with a `VALUES ?p { ... }` list yields exactly one row per (ship, property, value) — 667 rows for 60 ships. Do **not** use one `OPTIONAL` block per property: that multiplies rows for any ship with several multi-valued properties (the same defect found and avoided in the Wikidata adapter).
- **Chunking is mandatory.** The public endpoint caps result rows (~10k). At ~11 rows/ship, `CHUNK_SIZE = 200` yields ~2,200 rows per request — comfortably safe, ~12 requests for the full fleet.
- **Field coverage among matched ships** (n=60): `shipArmament` 60/60, `shipTonsBurthen` 60/60, `dbo:length` 59/60, `dbo:shipBeam` 59/60, `shipFate` 59/60, `shipComplement` 58/60, `shipSailPlan` 58/60, `shipBuilder` 57/60, `dbo:builder` 53/60.
- **SPEC CORRECTION — there is no draught data.** The design spec lists a `draught` field, but `dbp:shipDraught`, `dbp:shipDraft`, and `dbo:draft` returned **zero rows** across every probe. `draught` is therefore **omitted from this plan**; all other spec'd fields are implemented. Flag this to the project owner rather than silently inventing a source for it.
- **Values arrive in three shapes and all three need handling:**
  - Clean literals: `dbo:length` → `'56.6928'`, `shipTonsBurthen` → `'2142'`.
  - **DBpedia resource URIs, not labels** — `shipSailPlan` is a URI in 57/58 cases (`'http://dbpedia.org/resource/Full-rigged_ship'`), `dbo:builder` in 64/64, `dbp:shipBuilder` in 18/62. These must be converted to text (`Full-rigged ship`).
  - Multi-line infobox wikitext: `shipArmament` → `'*28 guns comprising:\n*Upperdeck: 24 × 9-pounder guns\n*Quarterdeck: 4 × 3-pounder guns'`.
- **Junk is real and must be dropped, not stored.** `shipFate` is a malformed date fragment (`'--09-19'`, `'--05-23'`) in **40 of 65** observed values. Degenerate wikitext such as `'* ,\n*'` also occurs.
- **Same-source multi-values occur** (of 60 ships: 8 have multiple `dbo:builder`, 5 multiple `shipClass`, 5 multiple `shipFate`, 4 multiple `dbp:shipBuilder`). These are handled by the conflict mechanism, not by picking arbitrarily and discarding.
- **`guns` is only extractable for ~23% of matched ships** (3/60 plain integers + 11/60 explicitly stated totals such as `'*28 guns comprising:'`; 46/60 not extractable). Summing the per-deck `24 × 9-pounder` multipliers is deliberately not attempted — many entries span several eras or navies (`'*As built: ... *From 1780: ...'`, `'*Royal Navy ... *Citoyen ...'`), so a naive sum would silently double-count. A low yield here is expected, not a bug.

## File Structure

- Create: `royal_navy_ships/cache.py` — raw-result cache load/save/canonicalize (shared)
- Create: `royal_navy_ships/sources/sparql.py` — SPARQL-over-HTTP client + chunking (shared)
- Create: `royal_navy_ships/sources/dbpedia.py` — the DBpedia adapter
- Modify: `royal_navy_ships/model.py` — descriptive fields, `field_sources`, `conflicts`, `set_field`
- Modify: `royal_navy_ships/sources/wikidata.py` — use the shared modules; record provenance
- Modify: `royal_navy_ships/pipeline.py` — run both adapters, commit both caches
- Delete: `getships.py`, `ship.py`
- Modify: `CLAUDE.md`, `README.md`

---

### Task 1: Extract shared SPARQL and cache modules

Pure refactor — no behavior change. `dbpedia.py` needs the HTTP client, chunking, and cache helpers that currently live inside `wikidata.py`; importing one adapter from another would be backwards coupling.

**Files:**
- Create: `royal_navy_ships/cache.py`
- Create: `royal_navy_ships/sources/sparql.py`
- Modify: `royal_navy_ships/sources/wikidata.py`
- Modify: `royal_navy_ships/pipeline.py`

**Interfaces:**
- Produces (consumed by Tasks 3–5): `sparql.run_query(endpoint: str, query: str, retries: int = 3, backoff_seconds: float = 2.0) -> dict`; `sparql.chunked(items: List[str], size: int) -> Iterator[List[str]]`; `cache.load(cache_path: Path) -> Optional[dict]`; `cache.save(cache_path: Path, raw: dict) -> None`; `cache.canonicalize(raw: dict) -> dict`.
- Unchanged for callers: `wikidata.fetch_ships(cache_path: Path = CACHE_PATH) -> Tuple[List[Ship], bool, dict]`, `wikidata.CACHE_PATH`.

- [ ] **Step 1: Create the shared SPARQL client**

Create `royal_navy_ships/sources/sparql.py`:

```python
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
```

- [ ] **Step 2: Create the shared cache module**

Create `royal_navy_ships/cache.py`:

```python
"""Raw source-result caching shared by all adapters.

Adapters never call `save` themselves: the pipeline commits caches only after
the dataset write succeeds, so a run that dies mid-write cannot leave a cache
falsely claiming the output is current.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("cache")


def load(cache_path: Path) -> Optional[dict]:
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("cache file %s is unreadable or corrupt; ignoring it", cache_path)
        return None


def save(cache_path: Path, raw: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, sort_keys=True)
    os.replace(tmp_path, cache_path)


def canonicalize(raw: dict) -> dict:
    """Sort each query's binding rows into a stable order so that comparing two
    raw results is insensitive to an endpoint's nondeterministic row order."""
    return {
        key: sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
        for key, rows in raw.items()
    }
```

- [ ] **Step 3: Point wikidata.py at the shared modules**

In `royal_navy_ships/sources/wikidata.py`, replace exactly the text shown below — the import block plus the two constants above `ROYAL_NAVY_QID`. Leave `RATING_CLASS_QIDS`, `CHUNK_SIZE`, and `CACHE_PATH`, which follow it, exactly as they are:

```python
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
```

with:

```python
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from royal_navy_ships import cache
from royal_navy_ships.model import Ship, ShipEvent, ShipName, new_ship_id
from royal_navy_ships.sources import sparql

logger = logging.getLogger("wikidata")

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

ROYAL_NAVY_QID = "Q172771"
```

Then delete these now-relocated definitions from `wikidata.py` entirely: `run_sparql_query`, `_chunked`, `load_cache`, `save_cache`, and `_canonicalize`.

Replace the three call sites of the deleted helpers:
- In `fetch_events`, change `for chunk in _chunked(ship_qids, CHUNK_SIZE):` to `for chunk in sparql.chunked(ship_qids, CHUNK_SIZE):` and `result = run_sparql_query(build_events_query(chunk))` to `result = sparql.run_query(SPARQL_ENDPOINT, build_events_query(chunk))`.
- In `fetch_armament`, change `for chunk in _chunked(ship_qids, CHUNK_SIZE):` to `for chunk in sparql.chunked(ship_qids, CHUNK_SIZE):` and `result = run_sparql_query(build_armament_query(chunk))` to `result = sparql.run_query(SPARQL_ENDPOINT, build_armament_query(chunk))`.
- In `fetch_ships`, change `candidates_result = run_sparql_query(build_candidates_query())` to `candidates_result = sparql.run_query(SPARQL_ENDPOINT, build_candidates_query())`, `raw = _canonicalize({` to `raw = cache.canonicalize({`, and `cached = load_cache(cache_path)` to `cached = cache.load(cache_path)`.

- [ ] **Step 4: Point pipeline.py at the shared cache module**

In `royal_navy_ships/pipeline.py`, replace:

```python
from royal_navy_ships.sources import wikidata
```

with:

```python
from royal_navy_ships import cache
from royal_navy_ships.sources import wikidata
```

and replace:

```python
    if changed:
        wikidata.save_cache(wikidata.CACHE_PATH, raw)
```

with:

```python
    if changed:
        cache.save(wikidata.CACHE_PATH, raw)
```

- [ ] **Step 5: Verify — imports resolve and nothing stale remains**

Run:
```bash
python3 -c "
import inspect
from royal_navy_ships import cache
from royal_navy_ships.sources import sparql, wikidata

for gone in ('run_sparql_query', '_chunked', 'load_cache', 'save_cache', '_canonicalize'):
    assert not hasattr(wikidata, gone), f'{gone} should have moved out of wikidata.py'
src = inspect.getsource(wikidata)
assert 'urllib' not in src, 'wikidata.py should no longer do HTTP itself'
assert callable(sparql.run_query) and callable(cache.save)
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 6: Verify — full live pipeline still works, unchanged**

Run (deletes local artifacts first so this is a true cold run; takes ~1 minute):
```bash
rm -f ships.json && rm -rf .cache
python3 -m royal_navy_ships.pipeline
python3 -c "
import json
ships = json.load(open('ships.json'))
print('total ships:', len(ships))
assert len(ships) > 2000, len(ships)
assert any(s['external_ids'].get('wikidata') == 'Q213958' for s in ships), 'HMS Victory missing'
print('OK')
"
```
Expected: a `Wrote NNNN ships to ships.json` log line with a count in the low 2000s, then `total ships: ...` and `OK`.

Run again to confirm the skip path still works:
```bash
python3 -m royal_navy_ships.pipeline
```
Expected: `No change detected and output already exists; skipping regeneration. Use --force to override.`

- [ ] **Step 7: Commit**

```bash
git add royal_navy_ships/cache.py royal_navy_ships/sources/sparql.py royal_navy_ships/sources/wikidata.py royal_navy_ships/pipeline.py
git commit -m "refactor: extract shared SPARQL client and cache helpers"
```

---

### Task 2: Descriptive fields, provenance, and conflict merging

**Files:**
- Modify: `royal_navy_ships/model.py`
- Modify: `royal_navy_ships/sources/wikidata.py`

**Interfaces:**
- Produces (consumed by Task 4): `Ship.set_field(name: str, value: Optional[str], source: str) -> None`; `MERGEABLE_FIELDS: frozenset`; new `Ship` attributes `armament`, `tonnage`, `length`, `beam`, `complement`, `sail_plan`, `builder`, `fate` (all `Optional[str] = None`), `field_sources: Dict[str, str]`, `conflicts: Dict[str, List[dict]]`.

- [ ] **Step 1: Add the fields and the merge method**

In `royal_navy_ships/model.py`, add this constant immediately after the `new_ship_id` function:

```python
# Scalar fields that carry a single canonical answer merged from one or more
# sources. Structural fields (names, events, external_ids) are not merged this
# way and are owned by the adapter that produced them.
MERGEABLE_FIELDS = frozenset({
    "guns",
    "rating",
    "notes",
    "armament",
    "tonnage",
    "length",
    "beam",
    "complement",
    "sail_plan",
    "builder",
    "fate",
})
```

Then replace the whole `Ship` dataclass field block:

```python
@dataclass
class Ship:
    id: str
    names: List[ShipName] = field(default_factory=list)
    guns: Optional[str] = None
    rating: Optional[str] = None
    notes: str = ""
    events: List[ShipEvent] = field(default_factory=list)
    external_ids: Dict[str, str] = field(default_factory=dict)
    rebuilt_from_id: Optional[str] = None
    rebuilt_to_id: Optional[str] = None
```

with:

```python
@dataclass
class Ship:
    id: str
    names: List[ShipName] = field(default_factory=list)
    guns: Optional[str] = None
    rating: Optional[str] = None
    notes: str = ""
    events: List[ShipEvent] = field(default_factory=list)
    external_ids: Dict[str, str] = field(default_factory=dict)
    rebuilt_from_id: Optional[str] = None
    rebuilt_to_id: Optional[str] = None
    armament: Optional[str] = None
    tonnage: Optional[str] = None
    length: Optional[str] = None
    beam: Optional[str] = None
    complement: Optional[str] = None
    sail_plan: Optional[str] = None
    builder: Optional[str] = None
    fate: Optional[str] = None
    field_sources: Dict[str, str] = field(default_factory=dict)
    conflicts: Dict[str, List[dict]] = field(default_factory=dict)

    def set_field(self, name: str, value: Optional[str], source: str) -> None:
        """Record `value` for scalar field `name`, attributed to `source`.

        The dataset answers "how many guns did this ship carry?", not "which
        sources mention guns" -- so the first source to supply a non-empty
        value owns the canonical field, and any later value that disagrees is
        preserved in `conflicts` instead of overwriting it or being dropped.
        A later source repeating the same value is corroboration, not a
        conflict. Empty values are ignored entirely.
        """
        if name not in MERGEABLE_FIELDS:
            raise ValueError(f"unknown mergeable field: {name!r}")
        if not value:
            return
        current = getattr(self, name)
        if not current:
            setattr(self, name, value)
            self.field_sources[name] = source
            return
        if current == value:
            return
        entry = {"value": value, "source": source}
        conflicting = self.conflicts.setdefault(name, [])
        if entry not in conflicting:
            conflicting.append(entry)
```

- [ ] **Step 2: Record provenance for the Wikidata-sourced fields**

In `royal_navy_ships/sources/wikidata.py`, replace the body of `to_ships`:

```python
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
```

with:

```python
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
```

- [ ] **Step 3: Verify the merge semantics**

Run:
```bash
python3 -c "
import json
from royal_navy_ships.model import Ship, new_ship_id

s = Ship(id=new_ship_id())

# first non-empty value wins and is attributed
s.set_field('guns', '104', 'wikidata')
assert s.guns == '104'
assert s.field_sources['guns'] == 'wikidata'

# a second source agreeing is corroboration, not a conflict
s.set_field('guns', '104', 'dbpedia')
assert s.conflicts == {}, s.conflicts

# a second source disagreeing is preserved, canonical answer unchanged
s.set_field('guns', '100', 'dbpedia')
assert s.guns == '104'
assert s.conflicts['guns'] == [{'value': '100', 'source': 'dbpedia'}], s.conflicts

# the identical conflict is not recorded twice
s.set_field('guns', '100', 'dbpedia')
assert len(s.conflicts['guns']) == 1

# empty values are ignored; a gap is still fillable afterwards
s.set_field('tonnage', None, 'dbpedia')
s.set_field('tonnage', '', 'dbpedia')
assert s.tonnage is None and 'tonnage' not in s.field_sources
s.set_field('tonnage', '2142', 'dbpedia')
assert s.tonnage == '2142' and s.field_sources['tonnage'] == 'dbpedia'

# unknown fields are a programming error, not a silent no-op
try:
    s.set_field('displacement', '1000', 'dbpedia')
    raise SystemExit('expected ValueError for unknown field')
except ValueError:
    pass

json.dumps(s.to_dict())  # must stay JSON-serializable
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 4: Verify provenance appears in the real dataset**

Run:
```bash
python3 -m royal_navy_ships.pipeline --force
python3 -c "
import json
ships = json.load(open('ships.json'))
rated = [s for s in ships if s['rating']]
assert rated, 'no ship has a rating'
assert all(s['field_sources'].get('rating') == 'wikidata' for s in rated)
gunned = [s for s in ships if s['guns']]
print('ships with rating:', len(rated), ' with guns:', len(gunned))
assert all(s['field_sources'].get('guns') == 'wikidata' for s in gunned)
print('OK')
"
```
Expected: a count line then `OK`. Note the `with guns:` number will be small — Wikidata's armament data is sparse, which is the gap Task 4 closes.

- [ ] **Step 5: Commit**

```bash
git add royal_navy_ships/model.py royal_navy_ships/sources/wikidata.py
git commit -m "feat: add descriptive ship fields with per-field provenance and conflict capture"
```

---

### Task 3: DBpedia adapter — query building and fetch

**Files:**
- Create: `royal_navy_ships/sources/dbpedia.py`

**Interfaces:**
- Consumes: `sparql.run_query`, `sparql.chunked` (Task 1).
- Produces (consumed by Task 4, appended to this same file): `SPARQL_ENDPOINT`, `CACHE_PATH`, `CHUNK_SIZE`, `DBO`, `DBP`, `RESOURCE_PREFIX`, `FIELD_PROPERTIES: Dict[str, Tuple[str, ...]]`, `QUERIED_PROPERTIES: Tuple[str, ...]`, `build_properties_query(ship_qids: List[str]) -> str`, `fetch_rows(ship_qids: List[str]) -> List[dict]`.

- [ ] **Step 1: Write the adapter's query layer**

Create `royal_navy_ships/sources/dbpedia.py`:

```python
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
```

- [ ] **Step 2: Verify against the live endpoint**

Run:
```bash
python3 -c "
from royal_navy_ships.sources import dbpedia

# HMS Victory (Q213958) and HMS Rose 1757 (Q5634103)
rows = dbpedia.fetch_rows(['Q213958', 'Q5634103'])
print('rows:', len(rows))

resources = {r['wd']['value'].rsplit('/', 1)[-1]: r['resource']['value'] for r in rows}
assert resources['Q213958'] == 'http://dbpedia.org/resource/HMS_Victory', resources
assert resources['Q5634103'] == 'http://dbpedia.org/resource/HMS_Rose_(1757)', resources

props = {r['p']['value'].rsplit('/', 1)[-1] for r in rows}
assert {'shipArmament', 'shipTonsBurthen', 'length', 'shipBeam'} <= props, sorted(props)

# every row must carry all four bindings -- no partial rows from a cross-product
assert all({'wd', 'resource', 'p', 'o'} <= set(r) for r in rows)
print('OK')
"
```
Expected: `rows:` a number between roughly 12 and 30 (about 9–11 rows per ship), then `OK`.

- [ ] **Step 3: Commit**

```bash
git add royal_navy_ships/sources/dbpedia.py
git commit -m "feat: add DBpedia adapter query layer with QID-based join"
```

---

### Task 4: DBpedia adapter — cleaning, parsing, and enrichment

**Files:**
- Modify: `royal_navy_ships/sources/dbpedia.py`

**Interfaces:**
- Consumes: `Ship.set_field` (Task 2); `FIELD_PROPERTIES`, `RESOURCE_PREFIX`, `CACHE_PATH`, `fetch_rows` (Task 3); `cache.canonicalize`, `cache.load` (Task 1).
- Produces (consumed by Task 5): `clean_value(value: str) -> Optional[str]`; `extract_gun_count(armament: str) -> Optional[str]`; `index_rows(rows: List[dict]) -> Dict[str, dict]`; `enrich(ships: List[Ship], indexed: Dict[str, dict]) -> int`; `fetch_enrichment(ships: List[Ship], cache_path: Path = CACHE_PATH) -> Tuple[bool, dict]`.

- [ ] **Step 1: Extend the import block**

In `royal_navy_ships/sources/dbpedia.py`, replace:

```python
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from royal_navy_ships.sources import sparql
```

with:

```python
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from royal_navy_ships import cache
from royal_navy_ships.model import Ship
from royal_navy_ships.sources import sparql
```

- [ ] **Step 2: Append the cleaning layer**

Append to the end of `royal_navy_ships/sources/dbpedia.py`:

```python


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
        text = TEMPLATE_RE.sub(" ", value)
        text = WIKILINK_RE.sub(lambda match: match.group(1), text)
        text = BULLET_RE.sub("", text)
        text = text.replace("\n", "; ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    text = SEPARATOR_RE.sub("; ", text).strip("; ").strip()
    if not text or not ALNUM_RE.search(text) or JUNK_DATE_RE.match(text):
        return None
    return text


def extract_gun_count(armament: str) -> Optional[str]:
    """Pull a total gun count out of a cleaned armament string, if one is stated.

    Accepts only a bare integer or an explicitly stated total ("28 guns
    comprising: ..."). Summing the per-deck "24 x 9-pounder" multipliers is
    deliberately not attempted: many entries cover several eras or navies
    ("As built: ... From 1780: ...", "Royal Navy ... Citoyen ..."), so a naive
    sum would silently double-count. Expect a total for roughly a quarter of
    matched ships; the full text is always kept in `armament` regardless.
    """
    if PLAIN_INT_RE.match(armament):
        return armament
    match = STATED_TOTAL_RE.match(armament)
    return match.group(1) if match else None
```

- [ ] **Step 3: Verify the cleaning rules against real observed values**

Run:
```bash
python3 -c "
from royal_navy_ships.sources.dbpedia import clean_value, extract_gun_count

# resource URIs become readable labels
assert clean_value('http://dbpedia.org/resource/Full-rigged_ship') == 'Full-rigged ship'
assert clean_value('http://dbpedia.org/resource/Chatham_Dockyard') == 'Chatham Dockyard'
assert clean_value('http://dbpedia.org/resource/HMS_Rose_(1757)') == 'HMS Rose (1757)'

# clean literals pass through untouched
assert clean_value('2142') == '2142'
assert clean_value('56.6928') == '56.6928'
assert clean_value('Hugh Blaydes, Hull, England') == 'Hugh Blaydes, Hull, England'

# multi-line infobox wikitext flattens to one readable line
got = clean_value('*28 guns comprising:\n*Upperdeck: 24 × 9-pounder guns\n*Quarterdeck: 4 × 3-pounder guns')
assert got == '28 guns comprising:; Upperdeck: 24 × 9-pounder guns; Quarterdeck: 4 × 3-pounder guns', repr(got)
assert clean_value('[[Chatham Dockyard|Chatham]]') == 'Chatham'
assert clean_value('Broken up {{circa}} 1836') == 'Broken up 1836'

# junk is dropped, not stored
assert clean_value('--09-19') is None
assert clean_value('--05-23') is None
assert clean_value('* ,\n*') is None
assert clean_value('') is None
assert clean_value('   ') is None

# gun totals: only bare integers and stated totals
assert extract_gun_count('20') == '20'
assert extract_gun_count('28 guns comprising:; Upperdeck: 24 × 9-pounder guns') == '28'
assert extract_gun_count('26 guns; Upper deck: 20 × 32-pounder gunnades') == '26'
assert extract_gun_count('Upper deck: 24 × 9-pounder guns; QD: 4 × 3-pounder guns') is None
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 4: Append the indexing and enrichment layer**

Append to the end of `royal_navy_ships/sources/dbpedia.py`:

```python


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
```

- [ ] **Step 5: Verify enrichment end-to-end on known ships**

Run:
```bash
python3 -c "
from royal_navy_ships.model import Ship, new_ship_id
from royal_navy_ships.sources import dbpedia

victory = Ship(id=new_ship_id(), external_ids={'wikidata': 'Q213958'})
rose = Ship(id=new_ship_id(), external_ids={'wikidata': 'Q5634103'})
orphan = Ship(id=new_ship_id(), external_ids={'wikidata': 'Q000000000'})
ships = [victory, rose, orphan]

indexed = dbpedia.index_rows(dbpedia.fetch_rows(['Q213958', 'Q5634103', 'Q000000000']))
count = dbpedia.enrich(ships, indexed)
assert count == 2, count

assert victory.external_ids['dbpedia'] == 'HMS_Victory'
assert victory.tonnage == '2142', victory.tonnage
assert victory.sail_plan == 'Full-rigged ship', victory.sail_plan
assert victory.armament and 'Gundeck' in victory.armament
assert victory.field_sources['tonnage'] == 'dbpedia'
print('Victory  complement=%r length=%r builder=%r' % (victory.complement, victory.length, victory.builder))

assert rose.tonnage == '449', rose.tonnage
assert rose.guns == '20', rose.guns          # armament was a bare integer
assert rose.field_sources['guns'] == 'dbpedia'
assert rose.fate is None or '--' not in rose.fate   # junk fate dropped
print('Rose     guns=%r complement=%r fate=%r' % (rose.guns, rose.complement, rose.fate))

# a ship with no DBpedia resource is untouched, not crashed
assert orphan.tonnage is None and 'dbpedia' not in orphan.external_ids
print('OK')
"
```
Expected: two printed detail lines then `OK`. `Victory` must show a non-`None` complement and length; `Rose` must show `guns='20'`.

- [ ] **Step 6: Commit**

```bash
git add royal_navy_ships/sources/dbpedia.py
git commit -m "feat: clean and merge DBpedia infobox values into canonical ships"
```

---

### Task 5: Wire DBpedia into the pipeline

**Files:**
- Modify: `royal_navy_ships/pipeline.py`

**Interfaces:**
- Consumes: `dbpedia.fetch_enrichment`, `dbpedia.CACHE_PATH` (Task 4); `wikidata.fetch_ships`, `wikidata.CACHE_PATH` (Task 1); `cache.save` (Task 1).

- [ ] **Step 1: Run both adapters and commit both caches**

In `royal_navy_ships/pipeline.py`, replace:

```python
from royal_navy_ships import cache
from royal_navy_ships.sources import wikidata
```

with:

```python
from royal_navy_ships import cache
from royal_navy_ships.sources import dbpedia, wikidata
```

Replace the `--force` help text:

```python
        help="Regenerate output even if the Wikidata result is unchanged from the cache",
```

with:

```python
        help="Regenerate output even if no source has changed since the last run",
```

Replace:

```python
    ships, changed, raw = wikidata.fetch_ships()
    logger.info("Fetched %d ships from Wikidata (changed since last cache: %s)", len(ships), changed)

    if not changed and args.output.exists() and not args.force:
```

with:

```python
    ships, wikidata_changed, wikidata_raw = wikidata.fetch_ships()
    logger.info(
        "Fetched %d ships from Wikidata (changed since last cache: %s)",
        len(ships),
        wikidata_changed,
    )

    dbpedia_changed, dbpedia_raw = dbpedia.fetch_enrichment(ships)
    logger.info("DBpedia changed since last cache: %s", dbpedia_changed)

    changed = wikidata_changed or dbpedia_changed

    if not changed and args.output.exists() and not args.force:
```

Replace:

```python
    if changed:
        cache.save(wikidata.CACHE_PATH, raw)
```

with:

```python
    if wikidata_changed:
        cache.save(wikidata.CACHE_PATH, wikidata_raw)
    if dbpedia_changed:
        cache.save(dbpedia.CACHE_PATH, dbpedia_raw)
```

- [ ] **Step 2: Run the full pipeline cold**

Run (allow a few minutes — roughly 25 Wikidata requests plus ~12 DBpedia requests):
```bash
rm -f ships.json && rm -rf .cache
time python3 -m royal_navy_ships.pipeline
```
Expected: an `Enriched NNNN of NNNN ships from DBpedia` line, then `Wrote NNNN ships to ships.json`. No traceback. Both `.cache/wikidata_raw.json` and `.cache/dbpedia_raw.json` should now exist.

- [ ] **Step 3: Verify the enriched dataset**

Run:
```bash
python3 -c "
import json
ships = json.load(open('ships.json'))
total = len(ships)
matched = [s for s in ships if 'dbpedia' in s['external_ids']]
print('total ships      :', total)
print('dbpedia matched  : %d (%.0f%%)' % (len(matched), 100*len(matched)/total))
for f in ('guns','armament','tonnage','length','beam','complement','sail_plan','builder','fate'):
    n = sum(1 for s in ships if s.get(f))
    print('  %-11s: %d' % (f, n))
conf = sum(1 for s in ships if s['conflicts'])
print('ships with conflicts:', conf)

assert len(matched) > total * 0.5, 'expected over half the fleet to match DBpedia'
assert sum(1 for s in ships if s.get('tonnage')) > 1000, 'tonnage coverage too low'

# every populated mergeable field must carry provenance
for s in ships:
    for f in ('guns','armament','tonnage','length','beam','complement','sail_plan','builder','fate','rating'):
        if s.get(f):
            assert f in s['field_sources'], (s['id'], f)

# no junk leaked into canonical fields
import re
junk = re.compile(r'^-{2}\d{2}-\d{2}\$')
assert not [s for s in ships if s.get('fate') and junk.match(s['fate'])], 'junk fate leaked'

v = [s for s in ships if s['external_ids'].get('wikidata') == 'Q213958'][0]
print('Victory:', v['tonnage'], '|', v['sail_plan'], '|', v['complement'])
assert v['tonnage'] == '2142'
print('OK')
"
```
Expected: coverage lines showing `dbpedia matched` above 50%, `tonnage`/`armament` in the low thousands, `guns` substantially higher than before this branch, and `OK`.

- [ ] **Step 4: Verify the skip path still works with two sources**

Run:
```bash
python3 -m royal_navy_ships.pipeline
```
Expected: `No change detected and output already exists; skipping regeneration. Use --force to override.`

If it does not skip, diagnose before continuing — the most likely cause is a source returning rows in a nondeterministic order that `cache.canonicalize` does not neutralize. Do not proceed with a broken skip path.

- [ ] **Step 5: Commit**

```bash
git add royal_navy_ships/pipeline.py
git commit -m "feat: run DBpedia enrichment as part of the pipeline"
```

---

### Task 6: Retire the legacy DBpedia scripts and update docs

**Files:**
- Delete: `getships.py`, `ship.py`
- Modify: `CLAUDE.md`, `README.md`

**Interfaces:** none (cleanup and documentation only).

- [ ] **Step 1: Delete the superseded scripts**

Both predate the package architecture and use `lookup.dbpedia.org` keyword search, which the QID join replaces.

```bash
git rm getships.py ship.py
```

- [ ] **Step 2: Update CLAUDE.md**

Five edits, each replacing the exact text shown.

**(a)** In `## What this repo is`, replace:

```
A Python package (`royal_navy_ships/`) that queries Wikidata's public SPARQL endpoint for Royal Navy sailing ships and generates a canonical, gitignored `ships.json` dataset (published via GitHub Releases, not tracked in git history).
```

with:

```
A Python package (`royal_navy_ships/`) that queries the public Wikidata and DBpedia SPARQL endpoints for Royal Navy sailing ships and generates a canonical, gitignored `ships.json` dataset (published via GitHub Releases, not tracked in git history).
```

**(b)** In `## Data pipeline`, replace this whole bullet:

```
- **`royal_navy_ships/sources/wikidata.py`** — the (currently only) source adapter. Queries Wikidata's public SPARQL endpoint live for Royal Navy ships in the sailing-ship rating classes (first-rate through sixth-rate, sloop-of-war, gun-brig -- see `RATING_CLASS_QIDS`), not a hardcoded date range. `fetch_ships()` compares the freshly-fetched result against the cache at `.cache/wikidata_raw.json` (gitignored) and reports whether it changed, but does not save the cache itself.
```

with:

```
- **`royal_navy_ships/sources/sparql.py` and `royal_navy_ships/cache.py`** — shared plumbing every adapter uses: a SPARQL-over-HTTP client with retry, and raw-result load/save/canonicalize. Adapters never write their own cache; `pipeline.py` commits caches only after the dataset write succeeds.
- **`royal_navy_ships/sources/wikidata.py`** — the primary source adapter, producing the ship list itself. Queries Wikidata's public SPARQL endpoint live for Royal Navy ships in the sailing-ship rating classes (first-rate through sixth-rate, sloop-of-war, gun-brig -- see `RATING_CLASS_QIDS`), not a hardcoded date range. `fetch_ships()` compares the freshly-fetched result against the cache at `.cache/wikidata_raw.json` (gitignored) and reports whether it changed, but does not save the cache itself.
- **`royal_navy_ships/sources/dbpedia.py`** — enrichment adapter. Joins DBpedia resources to ships via `owl:sameAs` on the Wikidata QID each record already carries (never by name), and merges Wikipedia infobox fields -- armament, tonnage, length, beam, complement, sail plan, builder, fate -- through `Ship.set_field`. Caches at `.cache/dbpedia_raw.json`, same contract as above.
```

**(c)** Replace:

```
No third-party dependencies -- the Wikidata client uses `urllib.request` from the standard library.

`getships.py` and `ship.py` (DBpedia enrichment, issue #4) are unaffected by this pipeline and still exist as separate, not-yet-wired-in scripts.
```

with:

```
No third-party dependencies -- the SPARQL client uses `urllib.request` from the standard library.

Every source adapter has the same shape: build query -> fetch rows -> parse/clean -> merge into canonical `Ship` records via `set_field`. Adding a source means writing one adapter and calling it from `pipeline.py`.
```

**(d)** In `## Key gotchas`, replace:

```
- **`.cache/wikidata_raw.json` and `ships.json` are both gitignored.** Regenerate locally via `python3 -m royal_navy_ships.pipeline`; don't expect either to be present in a fresh checkout.
- Two independent, overlapping DBpedia-enrichment implementations still exist (`getships.py` sync, `ship.py` async) -- neither is finished/wired into the pipeline. Check with the user which one (if either) they want extended before adding to both.
```

with:

```
- **Everything under `.cache/` and `ships.json` are gitignored.** Regenerate locally via `python3 -m royal_navy_ships.pipeline`; don't expect them in a fresh checkout.
```

**(e)** Append these bullets to the end of `## Key gotchas`:

```
- **Canonical fields answer the question, not "who said what".** `Ship.set_field` gives the first non-empty value the canonical slot and records later disagreements in `conflicts`, with per-field attribution in `field_sources`. Never assign a mergeable field directly -- go through `set_field` so provenance stays complete.
- **DBpedia values are raw Wikipedia infobox fragments and are frequently junk.** `dbp:shipFate` is a malformed `--MM-DD` date in roughly two thirds of cases; sail plans and builders arrive as resource URIs, not text. `clean_value` normalizes what it can and returns `None` for the rest -- junk must never reach a canonical field.
- **`Ship.guns` is only recoverable for about a quarter of DBpedia-matched ships.** Armament is usually a per-deck breakdown; only a bare integer or an explicitly stated total is parsed. Summing the `24 × 9-pounder` multipliers is deliberately avoided because many entries span several eras or navies and would double-count.
- **There is no draught data in DBpedia** (`dbp:shipDraught`, `dbp:shipDraft`, `dbo:draft` are all empty for this fleet), despite the design spec listing the field.
```

- [ ] **Step 3: Update README.md**

Four edits, all against the current file.

**(a)** Replace the opening description:

```markdown
A dataset (and the pipeline that generates it) of Royal Navy sailing-era ships — the
rating classes first-rate through sixth-rate, plus sloops and gun-brigs — sourced live
from [Wikidata](https://www.wikidata.org/).
```

with:

```markdown
A dataset (and the pipeline that generates it) of Royal Navy sailing-era ships — the
rating classes first-rate through sixth-rate, plus sloops and gun-brigs — sourced live
from [Wikidata](https://www.wikidata.org/) and enriched from
[DBpedia](https://www.dbpedia.org/).
```

**(b)** Replace:

```markdown
  Requires Python 3 and a network connection (queries Wikidata's public SPARQL
  endpoint). No third-party dependencies.
```

with:

```markdown
  Requires Python 3 and a network connection (queries the public Wikidata and
  DBpedia SPARQL endpoints). No third-party dependencies.
```

**(c)** Replace the whole per-ship field list — from the `- \`id\`` bullet through the `- \`notes\`` bullet — with:

```markdown
- `id` — a stable, dataset-internal identifier (a UUID), independent of any source.
- `external_ids` — identifiers in other systems, e.g. `{"wikidata": "Q213958",
  "dbpedia": "HMS_Victory"}`.
- `names` — a time-qualified list of names, since ships were frequently renamed or
  rebuilt under a new name.
- `events` — a timeline of significant events (launched, renamed, wrecked, broken up,
  etc.), each optionally dated.
- `rating` — the sailing-ship rating class (`First` .. `Sixth`, `Sloop`, `Gun-brig`).
- `guns` — gun count. Recorded only where a source states a total outright; the
  per-deck breakdown is not summed, because many descriptions span several eras or
  navies and would double-count. Absent for many ships.
- `armament` — the full armament description, usually a per-deck breakdown.
- `tonnage`, `length`, `beam`, `complement`, `sail_plan`, `builder`, `fate` —
  descriptive detail, largely from Wikipedia infoboxes via DBpedia. Present for most
  ships that have a Wikipedia article.
- `notes` — a short free-text description.
- `field_sources` — which source supplied each field above, e.g.
  `{"rating": "wikidata", "tonnage": "dbpedia"}`.
- `conflicts` — values from other sources that disagree with the canonical answer.
  Kept rather than discarded, so you can judge for yourself.
```

**(d)** Replace the closing three lines of the example JSON object:

```json
  "guns": "74",
  "rating": "Third",
  "notes": "French Téméraire-class ship of the line, captured by the Royal Navy at Trafalgar."
}
```

with:

```json
  "guns": "74",
  "armament": "Gun deck: 28 × 32-pounder guns; Upper gun deck: 30 × 18-pounder guns",
  "tonnage": "1885",
  "length": "52.4",
  "complement": "640",
  "sail_plan": "Full-rigged ship",
  "builder": "Rochefort",
  "fate": "Scuttled off Portsmouth, 2 December 1949",
  "rating": "Third",
  "notes": "French Téméraire-class ship of the line, captured by the Royal Navy at Trafalgar.",
  "field_sources": { "rating": "wikidata", "tonnage": "dbpedia", "guns": "dbpedia" },
  "conflicts": {}
}
```

Then append this section to the end of the file:

```markdown
## Sources

| Source | Contributes |
| --- | --- |
| [Wikidata](https://query.wikidata.org) | The ship list itself (rating classes + Royal Navy operator), name histories, and the event timeline |
| [DBpedia](https://dbpedia.org) | Wikipedia infobox detail — armament, tonnage, dimensions, complement, sail plan, builder, fate — joined on the Wikidata QID |

Roughly three quarters of the fleet has an English Wikipedia article and therefore a
DBpedia record; the remainder — mostly small sloops and gun-brigs — carries Wikidata
data only. Where two sources disagree, the canonical field keeps one answer and the
other is preserved in `conflicts`.
```

- [ ] **Step 4: Verify the docs match reality**

Run:
```bash
test ! -e getships.py && test ! -e ship.py && echo "legacy scripts gone"
grep -rn "lookup.dbpedia.org" --include=*.py --include=*.md . && echo "STALE REFERENCE FOUND" || echo "no stale lookup.dbpedia.org references"
grep -c "draught" CLAUDE.md
git status --short
```
Expected: `legacy scripts gone`; `no stale lookup.dbpedia.org references`; the `draught` count is `1` (the gotcha explaining its absence); `git status --short` shows the two deletions plus the two modified docs, and neither `ships.json` nor `.cache/` appears.

- [ ] **Step 5: Commit**

```bash
git add -A CLAUDE.md README.md getships.py ship.py
git commit -m "chore: retire legacy DBpedia scripts and document the enrichment source"
```
