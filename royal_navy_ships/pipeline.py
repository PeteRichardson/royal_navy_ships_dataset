#!/usr/bin/env python3
"""Orchestrates source adapters into the canonical ships.json dataset."""

import argparse
import json
import logging
import os
from pathlib import Path

from royal_navy_ships import cache
from royal_navy_ships.sources import dbpedia, wikidata

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
        help="Regenerate output even if no source has changed since the last run",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

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
        logger.info("No change detected and output already exists; skipping regeneration. Use --force to override.")
        return

    tmp_path = args.output.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump([ship.to_dict() for ship in ships], f, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp_path, args.output)
    logger.info("Wrote %d ships to %s", len(ships), args.output)

    if wikidata_changed:
        cache.save(wikidata.CACHE_PATH, wikidata_raw)
    if dbpedia_changed:
        cache.save(dbpedia.CACHE_PATH, dbpedia_raw)


if __name__ == "__main__":
    main()
