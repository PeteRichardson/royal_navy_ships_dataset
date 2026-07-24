# Canonical Ship Model + Wikidata Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `wikipedia_ship_list.txt`/`genships.py`/`ships.csv`/`nlp.py` pipeline with a `royal_navy_ships` Python package: a canonical `Ship` data model, a live Wikidata SPARQL source adapter, and a pipeline that writes a gitignored `ships.json` dataset — implementing GitHub issue #3 per `docs/specs/2026-07-24-canonical-ship-model-design.md`.

**Architecture:** A small package (`royal_navy_ships/`) with `model.py` (canonical dataclasses, shared by any future source adapter), `sources/wikidata.py` (the Wikidata SPARQL adapter: query building, HTTP fetch with retry, local raw-result caching, and parsing raw results into canonical `Ship` records), and `pipeline.py` (CLI entry point that runs the adapter and writes output). No third-party dependencies — `urllib.request`/`json` from the standard library, consistent with the zero-dependency style of the rest of the repo (neither `requests` nor `aiohttp`, used by `getships.py`/`ship.py`, are even installed in this environment, and there's no `requirements.txt`).

**Tech Stack:** Python 3 standard library only (`argparse`, `dataclasses`, `json`, `logging`, `pathlib`, `time`, `urllib`, `uuid`).

## Global Constraints

- No CSV export, no export-adapter abstraction (dropped from the original issue #3 scope — see the design doc).
- Both the raw Wikidata query cache and the generated `ships.json` are **gitignored**, never committed — the dataset is meant to be published via GitHub Releases, not tracked in git history.
- Filter Wikidata by ship *class* (the verified rating-system QIDs below), not by a hardcoded date range.
- No test framework exists in this repo. Verification steps in this plan are real, runnable Python snippets with expected output (some hit the live Wikidata endpoint — that's intentional and required, since this whole feature's correctness depends on real SPARQL behavior that was hand-verified during design; a mocked test would not have caught the two query-shape bugs found below).
- **Verified Wikidata facts this plan depends on** (checked live against `query.wikidata.org` and `www.wikidata.org` during design):
  - Royal Navy = `Q172771`.
  - Rating-class QIDs: first-rate `Q892367`, second-rate `Q892368`, third-rate `Q892492`, fourth-rate `Q892562`, fifth-rate frigate `Q892554`, sixth-rate frigate `Q892278`, sloop-of-war `Q928235`, gun-brig `Q130396697`.
  - Significant-event timeline: `?ship p:P793 ?es . ?es ps:P793 ?event .` with optional qualifiers `?es pq:P585 ?date` (point in time) and `?es pq:P1810 ?namedAs` (what the ship was called at that event) — confirmed on HMS Implacable (Q63218): keel laying → launch (named "Duguay-Trouin") → transfer (renamed "HMS Implacable") → name change ("Foudroyant") → destruction. **This timeline is the single source for names, start year, and end year/reason** — no separate name or launch-date property is queried.
  - Armament (`P520`/qualifier `P1114` guns count) exists but is **very sparse** — only 4 rows total for HMS Victory (a well-documented ship) out of an entire rating class, and those 4 rows sum to less than Victory's commonly-cited 104 guns. Treat `guns` as best-effort/frequently-`None` from this source, not authoritative.
  - **Query-shape bug found and avoided:** combining the events `OPTIONAL` and an armament `OPTIONAL` as two independent top-level blocks in one query cross-products rows for any ship with both event and armament data. Fix: fetch events and armament as **separate queries**, merged by ship QID in Python.
  - **Query-shape bug found and avoided:** restricting a query to "ships matching the class filter" via `FILTER EXISTS { ... VALUES ?class {...} ... }` **times out** (60s+) on the public endpoint. Fix: fetch candidate ship QIDs first (cheap direct join, confirmed fast), then restrict follow-up queries via an explicit `VALUES ?ship { wd:Q1 wd:Q2 ... }` list of those QIDs (confirmed fast: 9 correct rows for a 3-ship test, no cross-product, no timeout).
  - The candidate query alone (class + operator, no event/armament join) returns **2270 ships** — confirmed via `COUNT(DISTINCT ?ship)`. This is a large increase over today's ~810-row `ships.csv`, since Wikidata's coverage is broader than the specific Wikipedia article that was originally scraped (includes sloops, gun-brigs, and other vessels that article never listed). Expected, not a bug.
  - The endpoint requires POST (not GET) for reliability once a query's `VALUES` list gets large — GET query strings for ~2270 QIDs would exceed practical URL length limits. All queries in this plan use POST.
- **Scope boundary on the multi-source matching interface:** the design doc says issue #3 should define how a source adapter declares "this is existing ship `id=X`" vs. "this is a new ship." This plan does **not** build that abstraction — with only one adapter (Wikidata) and no prior dataset to merge into, every run creates fresh `Ship` records via `new_ship_id()`. The `external_ids`/stable-`id` design is the foundation that makes matching *possible* later, but the actual matching/merge interface is deferred until issue #4 or #6 implements a second adapter with a real matching heuristic to inform its shape — building it speculatively now, against a single adapter that never needs it, would be guessing.

## File Structure

- Create: `royal_navy_ships/__init__.py` (empty)
- Create: `royal_navy_ships/model.py` — canonical `Ship`, `ShipName`, `ShipEvent` dataclasses, `new_ship_id()`
- Create: `royal_navy_ships/sources/__init__.py` (empty)
- Create: `royal_navy_ships/sources/wikidata.py` — SPARQL query building, HTTP fetch/retry, local caching, parsing into `Ship` records
- Create: `royal_navy_ships/pipeline.py` — CLI entry point
- Delete: `genships.py`, `wikipedia_ship_list.txt`, `ships.csv`, `nlp.py`
- Modify: `.gitignore` — add `.cache/` and `ships.json`
- Modify: `CLAUDE.md` — reflect the new architecture

---

### Task 1: Canonical Ship model

**Files:**
- Create: `royal_navy_ships/__init__.py`
- Create: `royal_navy_ships/model.py`

**Interfaces:**
- Produces (consumed by Task 2/3's `wikidata.py` and Task 4's `pipeline.py`): `ShipName(name: str, start_date: Optional[str] = None, end_date: Optional[str] = None)`; `ShipEvent(description: str, date: Optional[str] = None, named_as: Optional[str] = None)`; `Ship(id: str, names: List[ShipName] = [], guns: Optional[str] = None, rating: Optional[str] = None, notes: str = "", events: List[ShipEvent] = [], external_ids: Dict[str, str] = {}, rebuilt_from_id: Optional[str] = None, rebuilt_to_id: Optional[str] = None)` with properties `.current_name`, `.start_year`, `.end_year`, `.end_reason` and method `.to_dict()`; module function `new_ship_id() -> str`.

- [ ] **Step 1: Create the package marker**

Create `royal_navy_ships/__init__.py` (empty file — just makes the directory an importable package):

```python
```

- [ ] **Step 2: Write the canonical model**

Create `royal_navy_ships/model.py`:

```python
"""Canonical Ship data model shared by all source adapters."""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


def new_ship_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ShipName:
    name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@dataclass
class ShipEvent:
    description: str
    date: Optional[str] = None
    named_as: Optional[str] = None


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

    @property
    def current_name(self) -> Optional[str]:
        return self.names[-1].name if self.names else None

    def _dated_events(self) -> List[ShipEvent]:
        return sorted((e for e in self.events if e.date), key=lambda e: e.date)

    @property
    def start_year(self) -> Optional[int]:
        dated = self._dated_events()
        return int(dated[0].date[:4]) if dated else None

    @property
    def end_year(self) -> Optional[int]:
        dated = self._dated_events()
        return int(dated[-1].date[:4]) if dated else None

    @property
    def end_reason(self) -> Optional[str]:
        dated = self._dated_events()
        return dated[-1].description if dated else None

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 3: Verify the model behaves correctly**

Run:
```bash
python3 -c "
from royal_navy_ships.model import Ship, ShipName, ShipEvent, new_ship_id

s = Ship(
    id=new_ship_id(),
    names=[ShipName(name='Duguay-Trouin', start_date='1800-03-24', end_date='1805-11-03'),
           ShipName(name='HMS Implacable', start_date='1805-11-03', end_date='1943-01-01'),
           ShipName(name='Foudroyant', start_date='1943-01-01')],
    events=[ShipEvent(description='keel laying', date='1797-01-01'),
            ShipEvent(description='ship launching', date='1800-03-24', named_as='Duguay-Trouin'),
            ShipEvent(description='destruction', date='1949-12-02')],
    external_ids={'wikidata': 'Q63218'},
)
assert s.current_name == 'Foudroyant'
assert s.start_year == 1797
assert s.end_year == 1949
assert s.end_reason == 'destruction'
import json
json.dumps(s.to_dict())  # must not raise
print('OK')
"
```
Expected output: `OK` (no `AssertionError`, no exception from `json.dumps`).

- [ ] **Step 4: Commit**

```bash
git add royal_navy_ships/__init__.py royal_navy_ships/model.py
git commit -m "feat: add canonical Ship data model"
```

---

### Task 2: Wikidata SPARQL client (query building + HTTP fetch)

**Files:**
- Create: `royal_navy_ships/sources/__init__.py`
- Create: `royal_navy_ships/sources/wikidata.py`

**Interfaces:**
- Produces (consumed by Task 3, added to this same file): `RATING_CLASS_QIDS: Dict[str, str]`; `run_sparql_query(query: str) -> dict`; `build_candidates_query() -> str`; `build_events_query(ship_qids: List[str]) -> str`; `build_armament_query(ship_qids: List[str]) -> str`; `fetch_events(ship_qids: List[str]) -> List[dict]`; `fetch_armament(ship_qids: List[str]) -> List[dict]`.

- [ ] **Step 1: Create the package marker**

Create `royal_navy_ships/sources/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the SPARQL client**

Create `royal_navy_ships/sources/wikidata.py`:

```python
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
```

- [ ] **Step 3: Verify against the live endpoint**

Run:
```bash
python3 -c "
from royal_navy_ships.sources import wikidata

result = wikidata.run_sparql_query(wikidata.build_events_query(['Q63218']))
rows = result['results']['bindings']
print(len(rows), 'rows')
labels = sorted(r['eventLabel']['value'] for r in rows)
print(labels)
"
```
Expected output: `5 rows` followed by a list containing `'destruction'`, `'keel laying'`, `'name change'`, `'ship launching'`, `'transfer'` (HMS Implacable's known event timeline, verified during design).

- [ ] **Step 4: Commit**

```bash
git add royal_navy_ships/sources/__init__.py royal_navy_ships/sources/wikidata.py
git commit -m "feat: add Wikidata SPARQL client (query building + HTTP fetch)"
```

---

### Task 3: Wikidata parsing + local caching

**Files:**
- Modify: `royal_navy_ships/sources/wikidata.py` (add parsing + caching functions below the fetch code from Task 2)

**Interfaces:**
- Consumes: `Ship`, `ShipName`, `ShipEvent`, `new_ship_id` from `royal_navy_ships.model` (Task 1); `RATING_CLASS_QIDS`, `run_sparql_query`, `build_candidates_query`, `fetch_events`, `fetch_armament` from this same file (Task 2).
- Produces (consumed by Task 4's `pipeline.py`): `CACHE_PATH: Path`; `fetch_ships(cache_path: Path = CACHE_PATH) -> Tuple[List[Ship], bool]` — the `bool` is `True` if the fetched result differs from the cache.

- [ ] **Step 1: Add the model import and cache path constant**

In `royal_navy_ships/sources/wikidata.py`, replace:

```python
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional
```

with:

```python
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from royal_navy_ships.model import Ship, ShipEvent, ShipName, new_ship_id
```

Then, immediately after the `CHUNK_SIZE = 200` line, add:

```python

CACHE_PATH = Path(".cache/wikidata_raw.json")
```

- [ ] **Step 2: Add parsing functions**

At the end of `royal_navy_ships/sources/wikidata.py`, append:

```python

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
    with cache_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_path: Path, raw: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, sort_keys=True)


def fetch_ships(cache_path: Path = CACHE_PATH) -> Tuple[List[Ship], bool]:
    """Fetch ships from Wikidata. Returns (ships, changed) -- changed is False
    if the freshly-fetched raw result is identical to what's cached on disk."""
    candidates_result = run_sparql_query(build_candidates_query())
    candidate_rows = candidates_result["results"]["bindings"]
    ship_qids = [_qid_from_uri(row["ship"]["value"]) for row in candidate_rows]

    raw = {
        "candidates": candidate_rows,
        "events": fetch_events(ship_qids),
        "armament": fetch_armament(ship_qids),
    }

    cached = load_cache(cache_path)
    changed = raw != cached
    if changed:
        save_cache(cache_path, raw)

    ships = parse_candidates(raw["candidates"])
    attach_events(ships, raw["events"])
    attach_armament(ships, raw["armament"])
    return to_ships(ships), changed
```

- [ ] **Step 3: Verify parsing logic with a small live fetch**

Run:
```bash
python3 -c "
from royal_navy_ships.sources import wikidata

# Directly exercise the parse pipeline without the full 2270-ship candidate fetch,
# by feeding it a small hand-picked ship QID set (same pattern fetch_ships uses).
ship_qids = ['Q63218']
candidates_raw = [{
    'ship': {'value': 'http://www.wikidata.org/entity/Q63218'},
    'shipLabel': {'value': 'HMS Implacable'},
    'shipDescription': {'value': 'Royal Navy ship'},
    'class': {'value': 'http://www.wikidata.org/entity/Q892367'},
}]
ships = wikidata.parse_candidates(candidates_raw)
wikidata.attach_events(ships, wikidata.fetch_events(ship_qids))
wikidata.attach_armament(ships, wikidata.fetch_armament(ship_qids))
result = wikidata.to_ships(ships)

assert len(result) == 1
ship = result[0]
names = [n.name for n in ship.names]
print('names:', names)
print('start_year:', ship.start_year, 'end_year:', ship.end_year, 'end_reason:', ship.end_reason)
print('external_ids:', ship.external_ids)
assert names == ['Duguay-Trouin', 'HMS Implacable', 'Foudroyant']
assert ship.start_year == 1797
assert ship.end_year == 1949
assert ship.external_ids == {'wikidata': 'Q63218'}
print('OK')
"
```
Expected output ends with `OK`; the printed `names` list must be exactly `['Duguay-Trouin', 'HMS Implacable', 'Foudroyant']` in that order, confirming the event-timeline-derived name history reconstruction works correctly against real data.

- [ ] **Step 4: Commit**

```bash
git add royal_navy_ships/sources/wikidata.py
git commit -m "feat: parse Wikidata SPARQL results into canonical Ship records, with local caching"
```

---

### Task 4: Pipeline orchestration

**Files:**
- Create: `royal_navy_ships/pipeline.py`

**Interfaces:**
- Consumes: `wikidata.fetch_ships()` from Task 3.

- [ ] **Step 1: Write the pipeline CLI**

Create `royal_navy_ships/pipeline.py`:

```python
#!/usr/bin/env python3
"""Orchestrates source adapters into the canonical ships.json dataset."""

import argparse
import json
import logging
from pathlib import Path

from royal_navy_ships.sources import wikidata

logger = logging.getLogger("pipeline")

OUTPUT_PATH = Path("ships.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Where to write the canonical ships.json dataset (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate output even if the Wikidata result is unchanged from the cache",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    ships, changed = wikidata.fetch_ships()
    logger.info("Fetched %d ships from Wikidata (changed since last cache: %s)", len(ships), changed)

    if not changed and args.output.exists() and not args.force:
        logger.info("No change detected and output already exists; skipping regeneration. Use --force to override.")
        return

    with args.output.open("w", encoding="utf-8") as f:
        json.dump([ship.to_dict() for ship in ships], f, indent=2, sort_keys=True, ensure_ascii=False)
    logger.info("Wrote %d ships to %s", len(ships), args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full pipeline for real**

Run:
```bash
time python3 -m royal_navy_ships.pipeline
```
Expected: completes without traceback (this fetches all ~2270 candidate ships plus their events/armament in ~12-request chunks each -- allow a few minutes), ends with a log line like `Wrote 2270 ships to ships.json` (exact count may differ slightly if Wikidata has changed since design-time verification).

Run:
```bash
python3 -c "
import json
ships = json.load(open('ships.json'))
print('total ships:', len(ships))
victory = [s for s in ships if s['external_ids'].get('wikidata') == 'Q213958']
print('HMS Victory found:', len(victory) == 1)
if victory:
    print('Victory names:', [n['name'] for n in victory[0]['names']])
"
```
Expected: `total ships:` a number in the low thousands; `HMS Victory found: True`.

- [ ] **Step 3: Verify the cache-hit skip path**

Run immediately again (no Wikidata changes expected in this short window):
```bash
python3 -m royal_navy_ships.pipeline
```
Expected: log line `No change detected and output already exists; skipping regeneration. Use --force to override.` — confirms the diff-and-skip caching behaves as designed.

- [ ] **Step 4: Commit**

```bash
git add royal_navy_ships/pipeline.py
git commit -m "feat: add pipeline CLI to generate ships.json from the Wikidata adapter"
```

---

### Task 5: Retire the old static-file pipeline

**Files:**
- Delete: `genships.py`, `wikipedia_ship_list.txt`, `ships.csv`, `nlp.py`
- Modify: `.gitignore`

**Interfaces:** none (cleanup only).

- [ ] **Step 1: Delete the retired files**

```bash
git rm genships.py wikipedia_ship_list.txt ships.csv nlp.py
```

- [ ] **Step 2: Gitignore the generated artifacts**

In `.gitignore`, replace:

```
venv/
*.log
```

with:

```
venv/
*.log
.cache/
ships.json
```

- [ ] **Step 3: Verify**

Run:
```bash
git status --short
```
Expected: shows `D  genships.py`, `D  wikipedia_ship_list.txt`, `D  ships.csv`, `D  nlp.py` staged for deletion, `M .gitignore`, and `ships.json`/`.cache/` do NOT appear as untracked (confirming they're now ignored).

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: retire static-file pipeline (genships.py, nlp.py, wikipedia_ship_list.txt, ships.csv)"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** none (doc-only change).

- [ ] **Step 1: Rewrite the pipeline description and gotchas**

Replace the entire `## Data pipeline` and `## Key gotchas` sections of `CLAUDE.md` with:

```markdown
## Data pipeline

- **`royal_navy_ships/model.py`** — canonical `Ship`/`ShipName`/`ShipEvent` dataclasses shared by all source adapters. A ship's name is a time-qualified list (`names`), not a single field, since ships were often renamed; `start_year`/`end_year`/`end_reason` are derived properties from the event timeline, not stored fields.
- **`royal_navy_ships/sources/wikidata.py`** — the (currently only) source adapter. Queries Wikidata's public SPARQL endpoint live for Royal Navy ships in the sailing-ship rating classes (first-rate through sixth-rate, sloop-of-war, gun-brig -- see `RATING_CLASS_QIDS`), not a hardcoded date range. Caches the raw SPARQL result at `.cache/wikidata_raw.json` (gitignored) and skips regenerating output if nothing changed since the last run.
- **`royal_navy_ships/pipeline.py`** — CLI entry point. Run via `python3 -m royal_navy_ships.pipeline` from the repo root. Writes `ships.json` (gitignored -- the dataset is published via GitHub Releases, not tracked in git history).

No third-party dependencies -- the Wikidata client uses `urllib.request` from the standard library.

`getships.py` and `ship.py` (DBpedia enrichment, issue #4) are unaffected by this pipeline and still exist as separate, not-yet-wired-in scripts.

## Key gotchas

- **Wikidata's armament data (`P520`/`P1114`) is very sparse.** `Ship.guns` is frequently `None`; where present, treat it as best-effort, not authoritative -- it was found during design to undercount even well-documented ships like HMS Victory.
- **A ship's `names` list is derived entirely from its Wikidata event timeline's `named_as` qualifiers** (`P1810` on `P793` significant-event statements), not from a separate name property. A ship with no tagged rename events gets a single `ShipName` from its current Wikidata label.
- **`.cache/wikidata_raw.json` and `ships.json` are both gitignored.** Regenerate locally via `python3 -m royal_navy_ships.pipeline`; don't expect either to be present in a fresh checkout.
- Two independent, overlapping DBpedia-enrichment implementations still exist (`getships.py` sync, `ship.py` async) -- neither is finished/wired into the pipeline. Check with the user which one (if either) they want extended before adding to both.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for the Wikidata-based pipeline"
```
