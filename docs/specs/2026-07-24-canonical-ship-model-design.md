# Canonical Ship Model + Wikidata Ingestion — Revised Issue #3 Design

## Context

GitHub issue #3 ("Rearchitect for pluggable data sources, JSON canonical store, CSV export") was filed with an initial scope: a canonical `Ship` dataclass, JSON/JSONL as the on-disk store, a source-adapter interface, a CSV export adapter, and a single-pipeline-invocation execution model.

Before implementing it, three new ideas surfaced that materially change or deepen that scope:

1. **Dynamic Wikidata ingest** — the current `genships.py`/`wikipedia_ship_list.txt` pipeline stage parses a Wikipedia article that was hand-copied into the repo years ago and has since drifted out of sync (see PR #8, which found `ships.csv` had been stale relative to its own source file since 2018). Rather than maintaining a static committed text file, pull live data from Wikidata via SPARQL instead.
2. **Learn from existing ship data models** — before locking in field names/structure for the canonical `Ship` model, review how Wikidata, threedecks.org, and The National Archives (UK) model ship data, particularly how they each handle a ship being renamed during its career.
3. **Future graph database (Ships/Ports/People)** — a much larger, separate feature. This is explicitly **out of scope** for this design; it's deferred to issue #9, which depends on this work and will be brainstormed separately.

This document supersedes issue #3's originally filed scope on the points below; issue #3's GitHub body has been updated to match.

## Research findings (informing the model below)

Reviewed three sources for how they model ship identity, especially renames:

- **Wikidata**: one item per physical hull for its entire life. Name is not a single field — it's a repeatable, time-qualified property (name + operator-at-the-time), plus a general "significant event" timeline where each event can be tagged with what the ship was called at that moment. Separate items exist only when a *different hull* later reuses a traditional name (e.g. eleven distinct "HMS Leopard" items).
- **threedecks.org**: a pure rename (same hull) is logged as a dated row in that ship's existing service-history log. A genuine *rebuild* (new hull) gets a new, separately linked page, cross-referenced via "Becomes"/"Broken up to rebuild."
- **The National Archives (UK) Discovery catalogue**: could not be verified directly (client-rendered SPA, blocked automated fetches). Search-snippet evidence suggests archival records are organized per-document (musters, logs) rather than per-ship-entity, cross-referenced by pennant/official numbers since names changed frequently. Not directly reusable as an entity model, but supports keeping room for archival cross-references per ship.

**Adopted:** Wikidata's pattern (one record per hull, time-qualified names, general event timeline) is the backbone. threedecks' rename-vs-rebuild distinction is layered on top as an explicit cross-reference field.

## Design

### 1. Data source & pipeline execution

- The **Wikidata SPARQL query becomes the primary/first source adapter**, replacing `genships.py`'s static-file parsing of `wikipedia_ship_list.txt` entirely (no fallback to the static file — see Cache policy below for why).
- **Filter by ship class, not by date range.** Verified via live SPARQL queries and entity search that Wikidata classifies Royal Navy ships into rating-system types — `first-rate` (Q...), `second-rate`, `third-rate`, `fourth-rate` (Q892562), `fifth-rate frigate`, `sixth-rate frigate`, `sloop-of-war`, `gun-brig`, etc. — distinct from later classes (`ironclad warship`, `battleship`, `cruiser`, `destroyer`, `submarine`, `Dreadnought`). Filtering by these rating classes (`wdt:P31`) + operator = Royal Navy (`wdt:P137 wd:Q172771`) captures the sailing-ship era on its own real domain boundary — the rating system itself stopped being used once ships moved to steam/ironclad — rather than an arbitrary hardcoded 1663–1860 range (which was never a real requirement, just an artifact of what happened to be on the Wikipedia page originally scraped). Implementation should look up and pin the exact QID for each rating class rather than relying on label matching, since labels can have variants (e.g. "fifth-rate" vs. "fifth-rate frigate").
- **Cache policy:** the pipeline assumes live network access is available whenever it runs (no offline mode required). The raw SPARQL query result is cached locally, **gitignored** (not committed) — committing it would recreate the exact staleness problem this migration exists to fix (a checked-in snapshot starts drifting the moment it's committed, as happened with `wikipedia_ship_list.txt` since 2018). On each run: always execute the (cheap, fast) SPARQL query; if the result is identical to the cached copy, skip regenerating downstream output. No separate revision-polling mechanism against Wikidata's edit history is needed — real content changes to the relevant Wikipedia article were found to happen only ~5–10 times/year, so the simple "always query, diff, skip if unchanged" approach is proportionate.
- Stays a **single pipeline invocation** that runs all source adapters and merges into the canonical model (per issue #3's original scope), with concurrency where it's natural — this is one SPARQL call for the Wikidata source; DBpedia (issue #4) already uses `asyncio`/`aiohttp` for per-ship HTTP calls.

### 2. Canonical Ship model

Replaces today's flat `nlp.py` `Ship` dataclass (which has a single fixed `name`, a sequential non-stable `id`, and unstructured `ShipEvent`s). New shape:

- **`id`** — a stable internal identifier (e.g. a short random ID such as a UUID4), generated by us. Deliberately **not** the ship's name (names change over a ship's life) and **not** borrowed wholesale from any single external source's ID scheme (external IDs can be merged or redirected — Wikidata items do get merged when duplicates are discovered).
- **`external_ids`** — a dict of cross-references to source-specific identifiers, e.g. `{"wikidata": "Q213958", "dbpedia": "...", "threedecks": "..."}`. Populated by whichever adapter sourced or matched the record. Extensible per-source as richer sources (e.g. a future National Archives adapter, which may need multiple archival document references per ship) are added later.
- **`names`** — a list of `{name, start_date, end_date}` records, replacing the single fixed `name` field. A ship is findable by any name it held during its career, matching Wikidata's own repeatable/time-qualified name property.
- **Event timeline** — extends today's `ShipEvent` concept: general lifecycle events (launched, captured, renamed, scuttled, broken up, etc.), each optionally tagged with the name the ship was known by at that moment (mirrors Wikidata's event-qualifier pattern).
- **`rebuilt_from_id` / `rebuilt_to_id`** — optional cross-references to a *different* Ship record's `id`, used only for a genuine hull replacement (distinct from an in-place rename, which stays as an event on the same record). Following threedecks' distinction.
- **Carried forward from today's model:** `guns`, `rating`, `notes`.
- **Derived, not stored:** `end_year`/`end_reason` (today's separate fields) become derived from the event timeline's terminal event, rather than duplicated — avoids the two representations drifting apart.

### 3. Storage

- JSON/JSONL canonical store (per issue #3's original scope — unchanged).
- **No CSV export, no export-adapter abstraction, for v1.** Dropped from scope: `jq` (or similar) against the published JSON already covers ad hoc flattening/export needs, and there's no other concrete exporter requirement right now to justify a pluggable export-adapter interface. If a real export need shows up later (e.g. feeding the future Ships/Ports graph idea), that can define its own interface at that time.
- **The generated canonical JSON dataset itself is also gitignored, not committed to the repo.** Consistent with the raw-Wikidata caching decision: the dataset is published as a versioned artifact on **GitHub Releases**, not tracked in git history (which would otherwise grow large with every ship-data change, the way `ships.csv`'s commit history already has). Anyone wanting the dataset grabs the latest Release rather than rebuilding the pipeline themselves; anyone modifying the pipeline regenerates it locally.

### 4. Cross-issue considerations (flagged, not solved here)

- **Overlap with issue #4 (DBpedia enrichment):** Wikidata's structured properties (armament, builder, dimensions, etc.) may substantially overlap with what issue #4's DBpedia enrichment was originally meant to add. Once this Wikidata adapter exists, issue #4's scope should be revisited rather than assuming DBpedia enrichment is purely additive on top of it.
- **Matching interface for issues #4 and #6:** both DBpedia enrichment (#4) and manual book-sourced entries (#6) need a way to declare "this data is about existing ship `id=X`" vs. "this is a new ship not yet in the canonical dataset." This design's job is to define that matching *interface* (how a source adapter expresses a match/no-match decision against the canonical `id` space); the source-specific matching *heuristics* (DBpedia keyword-search disambiguation, book-entry human-confirm step) remain #4's and #6's implementation responsibility, unchanged from how they were originally scoped.

## Explicitly out of scope

- CSV export / export-adapter abstraction (dropped per above; can be revisited later if a concrete need arises).
- The Ships/Ports/People graph database idea — deferred to issue #9, to be brainstormed separately once this canonical model exists.
- Implementing issue #4's or #6's actual matching heuristics — only the interface they'll use is defined here.
- A National Archives (UK) source adapter — not currently a filed issue; the `external_ids` design leaves room for one later.

## Follow-up actions (completed)

1. ~~Update the GitHub issue #3 body to reflect this revised scope~~ — done, see [issue #3](https://github.com/PeteRichardson/royal_navy_ships_dataset/issues/3).
2. ~~File a new issue for the future Ships/Ports graph database idea~~ — done, see [issue #9](https://github.com/PeteRichardson/royal_navy_ships_dataset/issues/9).
