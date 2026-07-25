# DBpedia Enrichment — Issue #4 Design

## Context

Issue #4 ("Complete the DBpedia integration for richer per-ship data") was filed before the Wikidata migration (#3, PR #10). The design spec for #3 flagged that #4's scope needed revisiting once the Wikidata adapter existed. This document is that revisit, based on fresh empirical research (2026-07-25) against live DBpedia endpoints.

**Research findings that reshape the issue:**

- **DBpedia is still worth building — it fills exactly the fields Wikidata leaves empty.** DBpedia (derived from English Wikipedia infoboxes) has armament/guns, tonnage, dimensions (length/beam/draught), crew complement, sail plan, builder, and fate for sailing-era RN ships. Wikidata's armament data (`P520`/`P1114`) is very sparse — `guns` is `None` for most of our ~2270 ships — and it has none of the other fields.
- **Coverage: ~75% of the fleet.** 1721 of ~2280 ships have English Wikipedia sitelinks (and thus DBpedia resources): near-100% for rated first-through-fourth-rates, ~48% for sloops, ~61% for gun-brigs. The gap is ships without Wikipedia articles — unfixable from any Wikipedia-derived source.
- **The legacy scripts' approach is obsolete, not just unfinished.** `lookup.dbpedia.org` KeywordSearch still responds but is actively wrong (top hit for "HMS Bellerophon" is the 1907 dreadnought, not the 1786 third-rate). It's also unnecessary: DBpedia resources carry verified `owl:sameAs` links to Wikidata entities, so matching is a deterministic batched SPARQL join on the QIDs our records already have. Both `getships.py` (sync) and `ship.py` (async) are therefore deleted rather than consolidated — the original issue's "keep the async version" recommendation predates this finding.
- **The real work is cleaning.** `dbp:` values are raw infobox wikitext fragments; some are garbage (a `shipLength` of literally `"* ,\n*"`). `dbo:` ontology properties are typed and clean where they exist.

## Design

### 1. Data access & matching

- New `royal_navy_ships/sources/dbpedia.py` adapter, same layered shape as the Wikidata adapter (query build → fetch → parse → merge).
- **Matching is a deterministic batch join**: chunked `VALUES` queries against `https://dbpedia.org/sparql`, asking for `?resource owl:sameAs <wikidata-QID>` plus the target properties, for all ship QIDs (~12 chunked POST requests). Reuses the existing `run_sparql_query` POST/retry machinery, generalized to accept an endpoint URL. No name matching, no Lookup API.
- Ships with no DBpedia resource get no enrichment — partial data, no crash.
- Raw results cached at `.cache/dbpedia_raw.json` (gitignored) with the same canonicalize/diff/skip pattern as the Wikidata cache. The pipeline's skip logic becomes "skip only if *neither* source changed."
- `external_ids` gains `"dbpedia": "<resource name>"` (e.g. `"HMS_Victory"`) for matched ships.

### 2. Model changes (`model.py`)

- New optional canonical `Ship` fields, populated by whichever source has them: `tonnage`, `length`, `beam`, `draught`, `complement`, `sail_plan`, `builder`, `fate`, `armament` — all `Optional[str]` (strings for consistency with `guns`; unit normalization deferred).
- **`field_sources: Dict[str, str]`** — per-field provenance, e.g. `{"guns": "dbpedia", "rating": "wikidata"}`. Both adapters populate it from day one, so provenance is complete for every filled field.
- **`conflicts: Dict[str, List[dict]]`** — losing values with their source, e.g. `{"guns": [{"value": "100", "source": "wikidata"}]}`. Recorded only when two sources disagree on a non-empty value — never silently dropped.
- **Data-first principle** (per project owner): canonical fields hold *the answer* ("how many guns?"), not per-source namespaces. `jq .guns` and DuckDB queries stay clean; provenance and disagreements live in the parallel maps. This is the conflict-handling pattern issue #6 (book entries) will also follow.
- **Precedence for now**: Wikidata wins where it actually has a value; DBpedia fills gaps. A lone source's value wins by default. Full precedence policy across many sources (books, threedecks, ...) is deferred until those sources exist.

### 3. Parsing & cleaning policy

- **Prefer `dbo:` (ontology) properties where present** — typed and already clean (e.g. `dbo:length` in meters). Fall back to `dbp:` (raw infobox) values where `dbo:` is absent.
- **Conservative cleaning of `dbp:` values**: strip wikitext markup (`[[links]]`, `{{templates}}`, bullet characters, newlines), collapse whitespace. If the cleaned result is empty or degenerate, **drop the field for that ship** — never store junk in a canonical field.
- **`guns` specifically**: DBpedia armament is typically a per-deck list ("Gundeck: 30 × 32-pounders…"). Extract a total gun count into canonical `guns` only where a stated total or simple sum is confidently parseable; otherwise leave `guns` unfilled but keep the cleaned armament text in `armament` so the detail isn't lost.
- **No AI/LLM parsing in this issue** — deterministic string cleaning only. The messy tail can be revisited later (issue #6 builds AI-extraction machinery anyway; see also closed issue #5).

### 4. Pipeline wiring & cleanup

- `pipeline.py` runs both adapters in one invocation: Wikidata first (produces the ship list), then DBpedia enrichment (joins on QID, merges per the precedence rules). Single `ships.json` output, written atomically, caches committed only after a successful output write (preserving PR #10's transactional ordering across both caches).
- The skip decision considers both caches; `--force` still overrides.
- **Delete `getships.py` and `ship.py`** — the last two legacy scripts, obsoleted by the QID join. This completes the repo's migration to the package architecture.
- CLAUDE.md and README updated: the "two overlapping DBpedia scripts" gotcha disappears; data-shape docs gain the new fields + provenance/conflicts maps.
- Runtime: roughly doubles the pipeline's request count (~24 total); still a couple of minutes.

## Out of scope

- Unit normalization of tonnage/dimensions/lengths (stored as strings).
- AI-based armament parsing.
- Source-precedence policy beyond "Wikidata > DBpedia."
- Stable-id persistence across runs (issue #14) — noted here because enrichment makes the dataset richer and more join-worthy, increasing #14's urgency, but it remains separate work.

## Acceptance criteria

- Running the pipeline enriches matched ships with DBpedia-sourced fields; ~75% of ships gain at least one new field (spot-check: HMS Victory gets tonnage/complement/armament; HMS Bellerophon (1786) gets guns/tonnage; a no-article sloop is unchanged and uncrashed).
- Every filled canonical field has a `field_sources` entry; every genuine cross-source disagreement appears in `conflicts`.
- No garbage values in canonical fields (degenerate wikitext dropped).
- `getships.py` and `ship.py` no longer exist; no code references lookup.dbpedia.org.
- Cache/skip behavior works across both sources; unchanged double-source runs skip regeneration.
