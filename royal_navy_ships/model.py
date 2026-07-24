"""Canonical Ship data model shared by all source adapters."""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


def new_ship_id() -> str:
    return str(uuid.uuid4())


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
