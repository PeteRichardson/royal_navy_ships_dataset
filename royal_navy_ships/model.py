"""Canonical Ship data model shared by all source adapters."""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


def new_ship_id() -> str:
    return str(uuid.uuid4())


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
