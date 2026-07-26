"""Canonical Ship data model shared by all source adapters."""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


# Ship ids are derived rather than drawn at random, so a ship keeps the same id
# in every release and consumers can join across dataset versions. The namespace
# below is uuid5(NAMESPACE_URL, "https://github.com/PeteRichardson/royal_navy_ships_dataset"),
# written out as a literal because recomputing it from a string means an edit to
# that string silently renumbers the entire dataset. It must never change.
SHIP_ID_NAMESPACE = uuid.UUID("41714beb-335c-5c64-b798-3329efefc252")

# Which external identifier a ship's id is derived from, best first. Only the
# first match is used, so adding a system to the end never moves an existing
# ship's id -- but reordering this tuple would.
ID_SOURCE_PRECEDENCE = ("wikidata", "dbpedia")


def new_ship_id() -> str:
    """A fresh random id, for a ship with no stable external identifier."""
    return str(uuid.uuid4())


def ship_id(external_ids: Dict[str, str]) -> str:
    """A stable id derived from `external_ids`, or a random one if none apply.

    Deriving beats storing a QID-to-id map: there is no file to commit, keep in
    sync, or lose, the dataset is reproducible from a fresh checkout, and a ship
    that disappears from Wikidata and later returns is recognised as the same
    vessel rather than being issued a second id.

    The identifier system is part of the hashed key, so two systems that happen
    to issue the same string do not collide.
    """
    for system in ID_SOURCE_PRECEDENCE:
        value = external_ids.get(system)
        if value:
            return str(uuid.uuid5(SHIP_ID_NAMESPACE, f"{system}:{value}"))
    return new_ship_id()


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
