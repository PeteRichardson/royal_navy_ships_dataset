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

# Which source wins the canonical slot when two disagree -- lower wins. This is
# a declared policy, not a consequence of the order pipeline.main() happens to
# call the adapters in: hand-curated book entries are corrections by
# construction and must outrank a sparse Wikidata guess even though the book
# adapter runs last (cheap bulk sources first, expensive curated ones last).
SOURCE_PRIORITY: Dict[str, int] = {
    "book": 0,
    "wikidata": 1,
    "dbpedia": 2,
}

# An adapter not listed above ranks below every one that is, so a new source
# can never silently displace a curated value before its priority is declared.
UNKNOWN_SOURCE_PRIORITY = 99


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, UNKNOWN_SOURCE_PRIORITY)


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


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
    field_sources: Dict[str, List[str]] = field(default_factory=dict)
    conflicts: Dict[str, List[dict]] = field(default_factory=dict)

    def set_field(self, name: str, value: Optional[str], source: str) -> None:
        """Record `value` for scalar field `name`, attributed to `source`.

        The dataset answers "how many guns did this ship carry?", not "which
        sources mention guns" -- so one value owns the canonical slot and the
        rest are preserved in `conflicts` rather than dropped. Which one wins
        is decided by SOURCE_PRIORITY, so the result does not depend on the
        order the adapters happen to run in: a higher-priority value arriving
        late takes the slot and demotes the incumbent, and a lower-priority
        one becomes a conflict. Equal-priority disagreements keep the
        incumbent, which is what DBpedia emitting several values for one
        infobox field produces.

        A source repeating the canonical value is corroboration, and is
        appended to `field_sources[name]` rather than discarded -- that list
        is what separates "DBpedia disagrees" from "DBpedia agrees and also
        offers a second value", which are otherwise identical on the wire.
        Empty values are ignored entirely.
        """
        if name not in MERGEABLE_FIELDS:
            raise ValueError(f"unknown mergeable field: {name!r}")
        if not value:
            return
        current = getattr(self, name)
        if not current:
            self._promote(name, value, source)
            return
        if current == value:
            _append_unique(self.field_sources.setdefault(name, []), source)
            return
        if source_priority(source) < self._canonical_priority(name):
            self._demote(name, current)
            self._promote(name, value, source)
            return
        self._record_conflict(name, value, source)

    def _canonical_priority(self, name: str) -> int:
        """The best priority among the sources concurring on the canonical value."""
        sources = self.field_sources.get(name, [])
        return min((source_priority(s) for s in sources), default=UNKNOWN_SOURCE_PRIORITY)

    def _promote(self, name: str, value: str, source: str) -> None:
        """Give `value` the canonical slot, attributed to `source` plus any
        recorded conflict that turns out to agree with it -- a conflict entry
        must never restate the canonical answer as a disagreement with itself."""
        setattr(self, name, value)
        recorded = self.conflicts.get(name, [])
        self.field_sources[name] = [source]
        for entry in recorded:
            if entry["value"] == value:
                _append_unique(self.field_sources[name], entry["source"])
        remaining = [e for e in recorded if e["value"] != value]
        if remaining:
            self.conflicts[name] = remaining
        else:
            self.conflicts.pop(name, None)

    def _demote(self, name: str, value: str) -> None:
        """Move the outgoing canonical value into `conflicts`, once per source
        that concurred on it, so no attribution is lost when it is displaced."""
        for source in self.field_sources.get(name, []):
            self._record_conflict(name, value, source)

    def _record_conflict(self, name: str, value: str, source: str) -> None:
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
