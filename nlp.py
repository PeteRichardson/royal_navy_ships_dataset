#!/usr/bin/env python3
"""Parse ships.csv notes into structured ship events."""

import argparse
import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("NLP")

FINAL_EVENT_TEXTS = frozenset({
    "sunk by the Luftwaffe",
    "burnt and broken up",
    "cancelled",
    "destroyed by fire",
    "broken up",
    "sold",
    "scuttled",
    "foundered",
    "hulked",
    "sold for breaking",
    "wreck sold for breaking",
})

EVENT_RE = re.compile(r"(.*) ?([\d]{4})(-\d+)? ?\[?.*\]?$")
UNKNOWN_YEAR_MARKERS = frozenset({"?", "-"})


@dataclass
class ShipEvent:
    year: int
    text: str

    def is_final(self) -> bool:
        return self.text in FINAL_EVENT_TEXTS

    def __str__(self) -> str:
        return f"\t{self.year}: {self.text}"


@dataclass
class Ship:
    id: int
    name: str
    guns: str
    rating: str
    start_year: int
    end_year: int = 9999
    end_reason: str = ""
    notes: str = ""
    events: List[ShipEvent] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{self.id:4}] {self.name} ({self.start_year}, {self.guns}g)"


def parse_events(text: str) -> Tuple[List[ShipEvent], str, int, str]:
    events: List[ShipEvent] = []
    notes: List[str] = []
    end_year = 9999
    end_reason = ""

    text = text.replace(";", ".")
    for raw_clause in text.split("."):
        clause = raw_clause.strip()
        match = EVENT_RE.match(raw_clause)
        if match:
            event_text, event_year, _ = match.groups()
            event = ShipEvent(int(event_year), event_text.strip())
            events.append(event)
            if event.is_final():
                end_year = event.year
                end_reason = event.text
        elif raw_clause[0:2] != "ex-":
            notes.append(clause)

    return events, ". ".join(notes), end_year, end_reason


def parse_ship(ship_id: int, row: dict) -> Ship:
    raw_start_year = row["year_launched"]
    start_year = 9999 if raw_start_year in UNKNOWN_YEAR_MARKERS else int(raw_start_year)

    events, notes, end_year, end_reason = parse_events(row["notes"])

    return Ship(
        id=ship_id,
        name=row["name"],
        guns=row["guns"],
        rating=row["rating"],
        start_year=start_year,
        end_year=end_year,
        end_reason=end_reason,
        notes=notes,
        events=events,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        default=Path("ships.csv"),
        type=Path,
        help="ships.csv dataset to parse (default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    with args.input.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for ship_id, row in enumerate(reader, start=1):
            ship = parse_ship(ship_id, row)
            logger.info(ship)
            logger.debug(ship.notes)
            for event in ship.events:
                logger.debug(event)


if __name__ == "__main__":
    main()
