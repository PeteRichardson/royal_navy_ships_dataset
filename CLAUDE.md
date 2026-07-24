# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A small data pipeline that scrapes/parses a Wikipedia list of Royal Navy sailing ships (1663–1860) into `ships.csv`, then optionally enriches or exports that data. There is no build system, test suite, or package manifest — just standalone scripts run individually.

## Data pipeline

Scripts are pipeline stages, not a library — run them in this order, each consuming the previous stage's output file:

1. **`wikipedia_ship_list.txt`** — raw text pasted from a Wikipedia "List of wooden ships of the Royal Navy" style article. Sections are ship ratings (e.g. `First rates[edit]`), each followed by lines like:
   `Prince Royal 92 (1663) – rebuilt 1663. taken and burnt by the Dutch 1666.`
2. **`genships.py`** — regex-parses `wikipedia_ship_list.txt` into normalized CSV, printed to stdout (redirect to `ships.csv`). It tracks the current "rate" (First/Second/Third...) from `[edit]` section headers and applies it to subsequent ship lines. **Written in Python 2 syntax** (`print` statement, not a function) — will not run under Python 3 without porting.
3. **`ships.csv`** — the canonical dataset: `year_launched,name,guns,rating,notes`. This is the primary output artifact of the repo.
4. **`nlp.py`** — reads `ships.csv`, parses the free-text `notes` field into structured `ShipEvent`s (via regex extracting trailing 4-digit years per clause) to derive an end year/reason per ship (e.g. "broken up", "sunk", "wrecked" ⇒ terminal event), and writes the result to `ships.hyper`, a Tableau extract file, using the **deprecated** `tableausdk.HyperExtract` API. That SDK has been retired by Tableau in favor of `tableauhyperapi` — this script will not run against modern Tableau installs without porting. Also written in Python 2 syntax.
5. **`getships.py`** — for each ship name in `ships.csv`, queries `lookup.dbpedia.org`'s KeywordSearch API (`QueryClass=ship&QueryString=HMS%20<name>`) synchronously via `requests`, to cross-reference DBpedia ship entries. Currently just logs matches; `Ship.data_from_ships_csv` is an unimplemented stub.
6. **`ship.py`** — an async (`asyncio`/`aiohttp`) variant of the DBpedia enrichment in `getships.py`/`nlp.py`'s DBpedia lookup, additionally extracting structured fields (armament, displacement, builder, etc.) from DBpedia ontology (`dbo:`) and property (`dbp:`) predicates via `extract_details()`. This is the more complete enrichment path but isn't wired to write output anywhere — it only prints.

## Key gotchas

- **Mixed Python 2/3**: `genships.py` and `nlp.py` use Python 2 syntax (`print` statement, `"rb"` file mode expecting `str` not `bytes`). `getships.py` and `ship.py` are Python 3 (f-string-free but `.format()`-based, `async`/`await`). Check which interpreter a script needs before running it.
- **`nlp.py` requires `tableausdk`**, an EOL package — installing it on a modern system is likely to fail. If asked to regenerate `ships.hyper`, this needs porting to `tableauhyperapi` first.
- **`nlp.py:114`** unconditionally deletes any existing `ships.hyper` (`os.unlink`) before regenerating it — expect that file to be overwritten/removed if the script is run.
- **CSV parsing in `nlp.py`/`ship.py` assumes exactly 5 comma-separated fields** (`year_launched,name,guns,rating,notes`); ship notes containing commas will break the naive `line.split(",")` in `ship.py:Ship.__init__` (note `genships.py` defends against this by replacing `,` with `. ` in source text before emitting CSV).
- Two independent, overlapping DBpedia-enrichment implementations exist (`getships.py` sync, `ship.py` async) — neither is finished/wired into the CSV→Hyper pipeline. Check with the user which one (if either) they want extended before adding to both.
