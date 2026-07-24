# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A small data pipeline that scrapes/parses a Wikipedia list of Royal Navy sailing ships (1663–1860) into `ships.csv`, then optionally enriches or exports that data. There is no build system, test suite, or package manifest — just standalone scripts run individually.

## Data pipeline

Scripts are pipeline stages, not a library — run them in this order, each consuming the previous stage's output file:

1. **`wikipedia_ship_list.txt`** — raw text pasted from a Wikipedia "List of wooden ships of the Royal Navy" style article. Sections are ship ratings (e.g. `First rates[edit]`), each followed by lines like:
   `Prince Royal 92 (1663) – rebuilt 1663. taken and burnt by the Dutch 1666.`
2. **`genships.py`** — regex-parses `wikipedia_ship_list.txt` into normalized CSV, written to stdout (redirect to `ships.csv`) via the `csv` module. It tracks the current "rate" (First/Second/Third...) from `[edit]` section headers and applies it to subsequent ship lines. Python 3, structured as a pure parsing function (`parse_wikipedia_list`) returning a `ShipListing` dataclass, plus a thin `argparse`-based `main()`.
3. **`ships.csv`** — the canonical dataset: `year_launched,name,guns,rating,notes`. This is the primary output artifact of the repo.
4. **`nlp.py`** — reads `ships.csv` via `csv.DictReader`, parses the free-text `notes` field into structured `ShipEvent`s (via regex extracting trailing 4-digit years per clause) to derive an end year/reason per ship (e.g. "broken up", "sunk", "wrecked" ⇒ terminal event), and logs each parsed `Ship`. Python 3; `Ship`/`ShipEvent` are dataclasses with only JSON-serializable field types (str/int/list), and parsing lives in standalone functions (`parse_ship`, `parse_events`) rather than instance methods, ahead of issue #3 needing them as a source-adapter's core logic. The former Tableau Hyper export (`tableausdk.HyperExtract`) was removed — this script no longer writes any file, it just parses and logs.
5. **`getships.py`** — for each ship name in `ships.csv`, queries `lookup.dbpedia.org`'s KeywordSearch API (`QueryClass=ship&QueryString=HMS%20<name>`) synchronously via `requests`, to cross-reference DBpedia ship entries. Currently just logs matches; `Ship.data_from_ships_csv` is an unimplemented stub.
6. **`ship.py`** — an async (`asyncio`/`aiohttp`) variant of the DBpedia enrichment in `getships.py`/`nlp.py`'s DBpedia lookup, additionally extracting structured fields (armament, displacement, builder, etc.) from DBpedia ontology (`dbo:`) and property (`dbp:`) predicates via `extract_details()`. This is the more complete enrichment path but isn't wired to write output anywhere — it only prints.

## Key gotchas

- All four pipeline scripts (`genships.py`, `nlp.py`, `getships.py`, `ship.py`) are now Python 3.
- **`genships.py`'s ship-line regex requires a literal en dash (`–`)** between the year and the notes; lines in `wikipedia_ship_list.txt` using a plain hyphen (`-`) instead are silently skipped (logged at DEBUG level). This is a known, currently-accepted gap, not a bug to fix opportunistically.
- **`nlp.py`'s "ex-" clause handling is dead code**: it checks `raw_clause[0:2] != "ex-"` before appending a clause to notes, but a 2-character slice can never equal the 3-character string `"ex-"`, so the check always passes — clauses starting with `"ex-"` (e.g. a ship's former name, `"ex-Prince"`) are always kept in notes as plain text, never specially extracted. Inherited unchanged from the original Python 2 code; not something later scripts should "fix" without checking downstream impact on `end_year`/`end_reason` derivation.
- **CSV parsing in `ship.py` assumes exactly 5 comma-separated fields** (`year_launched,name,guns,rating,notes`) via naive `line.split(",")`; ship notes containing commas will break it (`genships.py` defends against this by replacing `,` with `. ` in source text before emitting CSV, and `nlp.py` now uses `csv.DictReader` rather than a naive split, so this only remains a risk in `ship.py`).
- Two independent, overlapping DBpedia-enrichment implementations exist (`getships.py` sync, `ship.py` async) — neither is finished/wired into the pipeline. Check with the user which one (if either) they want extended before adding to both.
