#!/usr/bin/env python3
"""Parse the Wikipedia wooden-ship list into the ships.csv dataset."""

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterable, Iterator, Optional

logger = logging.getLogger("genships")

RATE_HEADER_RE = re.compile(r"(.*)\[edit\]")
SHIP_LINE_RE = re.compile(r"([A-Za-z ]+) (\d+) \((.*)\) – (.*)$")


@dataclass
class ShipListing:
    year_launched: str
    name: str
    guns: str
    rating: str
    notes: str


def normalize_rating(raw_rating: str) -> str:
    rating = raw_rating
    rating = rating.replace(" rates", "")
    rating = rating.replace(" Rates", "")
    rating = rating.replace(" rate", "")
    return rating


def parse_ship_line(line: str, rating: str) -> Optional[ShipListing]:
    match = SHIP_LINE_RE.match(line)
    if not match:
        return None
    name, guns, year, notes = match.groups()
    if year.startswith("c."):
        notes = f"{year}. {notes}"
        year = year[3:]
    return ShipListing(year_launched=year, name=name, guns=guns, rating=rating, notes=notes)


def parse_wikipedia_list(lines: Iterable[str]) -> Iterator[ShipListing]:
    rating = ""
    for raw_line in lines:
        line = raw_line.replace(",", ". ")

        header_match = RATE_HEADER_RE.match(line)
        if header_match:
            rating = normalize_rating(header_match.groups()[0])
            continue

        listing = parse_ship_line(line, rating)
        if listing:
            yield listing
        else:
            logger.debug("no match, skipping: %r", raw_line)


def write_csv(listings: Iterable[ShipListing], out) -> None:
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([f.name for f in fields(ShipListing)])
    for listing in listings:
        writer.writerow([getattr(listing, f.name) for f in fields(ShipListing)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        default=Path("wikipedia_ship_list.txt"),
        type=Path,
        help="Wikipedia ship-list text file to parse (default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    with args.input.open("r", encoding="utf-8") as f:
        listings = parse_wikipedia_list(f)
        write_csv(listings, sys.stdout)


if __name__ == "__main__":
    main()
