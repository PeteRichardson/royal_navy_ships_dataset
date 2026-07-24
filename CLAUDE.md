# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A small data pipeline that scrapes/parses a Wikipedia list of Royal Navy sailing ships (1663–1860) into `ships.csv`, then optionally enriches or exports that data. There is no build system, test suite, or package manifest — just standalone scripts run individually.

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
