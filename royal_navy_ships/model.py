"""Canonical Ship data model shared by all source adapters."""

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple


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


# Wikidata event labels that actually end a ship's existence. `end_year` and
# `end_reason` report nothing unless the last dated event is one of these --
# before that gate, "the last dated event" was reported unconditionally, so a
# ship whose only dated event was its launch claimed to have ended at launch.
#
# Drawn from the 31 distinct event labels the fleet actually produces, not
# invented: this is every one of them that states the vessel was destroyed or
# disposed of. Deliberately excluded are events a ship survives or outlives --
# `ship decommissioning` (the hull remains, and many were broken up years
# later), `capture` (HMS Implacable was captured *into* the Royal Navy and
# served another 144 years), `transfer`, `striking`, `explosion`, and named
# incidents like `Great Hurricane of 1780`, which record participation rather
# than fate.
#
# These are labels, not QIDs, so a Wikidata relabelling silently drops an
# event out of the set. Matching on event QIDs would be more robust but needs
# a QID on ShipEvent, which the events query already binds but the model does
# not carry.
FINAL_EVENT_LABELS = frozenset({
    "destruction",
    "scrapping",
    "ship breaking",
    "ship disposal",
    "shipwrecking",
    "sinking",
    "wreck",
})

# The Wikidata timeline records an ending for 35 ships; `fate` -- a Wikipedia
# infobox fragment, via DBpedia -- records one for about 880. So `end_year` and
# `end_reason` fall back to parsing `fate` when the timeline says nothing.
#
# `fate` is free text, but its grammar is narrow: a leading verb, then
# optionally a month and a year ("Broken up April 1811", "Sold for breaking up
# in 1816", "Wrecked, 1809"). Only that leading verb is read. It is what the
# sentence is *about*, so the year nearest it is the year that goes with it --
# "Recaptured 1776 and sold, possibly in 1777" mentions a terminal verb, but
# reading it would report a disposal that the string dates to a recapture.
#
# Values are FINAL_EVENT_LABELS entries, deliberately: `end_reason` is one
# vocabulary whatever source it came from, so a consumer can group on it, and
# `fate` itself keeps the fuller human-readable text either way.
#
# Verbs a ship *survives* are absent for the same reason `capture` is absent
# from FINAL_EVENT_LABELS -- `captured`, `taken`, `hulked`, `decommissioned`,
# `struck`, `returned`. So are verbs that state an ending without naming one:
# `lost`, `abandoned`, `disappeared`, `condemned`, `presumed`. They are
# terminal in meaning, but every label here asserts a *manner* of ending, and
# picking one for them would invent a detail the string withholds.
FATE_OUTCOMES: Dict[str, str] = {
    "breaking": "ship breaking",
    "broken": "ship breaking",
    "burned": "destruction",
    "burnt": "destruction",
    "destroyed": "destruction",
    "foundered": "sinking",
    "sank": "sinking",
    "scrapped": "scrapping",
    "scuttled": "destruction",
    "sold": "ship disposal",
    "sunk": "sinking",
    "wrecked": "shipwrecking",
}

# The fleet spans the 1500s to the early 1900s. Bounding the pattern rather
# than matching any four digits keeps a stray figure elsewhere in the string
# from being read as a date.
FATE_YEAR_RE = re.compile(r"\b1[5-9]\d{2}\b")
LEADING_WORD_RE = re.compile(r"[A-Za-z]+")

# Events are structural -- they are owned by the adapter that produced them
# rather than merged through `set_field`, so there is no `field_sources` entry
# to consult for an end derived from the timeline.
EVENT_SOURCE = "wikidata"


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

    def _final_event(self) -> Optional[ShipEvent]:
        """The event that ended the ship, or None if the timeline doesn't say.

        Gated on the *last* dated event rather than on any terminal event
        appearing somewhere in the timeline: a non-terminal event dated after
        a terminal one means the record is inconsistent, and reading an end
        out of it would assert more than the data supports.
        """
        dated = self._dated_events()
        if not dated:
            return None
        last = dated[-1]
        return last if last.description in FINAL_EVENT_LABELS else None

    def _fate_end(self) -> Optional[Tuple[Optional[int], str]]:
        """`(year, label)` read out of `fate`, or None if it states no ending.

        The year is optional and the label is not: a stated outcome with no
        date still answers "how did this ship end", and 21 ships in the
        current fleet are in exactly that position ("Sold", "Broken up").
        The reverse -- a year with no recognised outcome -- is not an ending
        at all, and is what "Last listed in 1808" and "Captured 1794" are.
        """
        if not self.fate:
            return None
        leading = LEADING_WORD_RE.match(self.fate)
        if leading is None:
            return None
        label = FATE_OUTCOMES.get(leading.group().lower())
        if label is None:
            return None
        year = FATE_YEAR_RE.search(self.fate)
        return (int(year.group()) if year else None, label)

    def _end(self) -> Optional[Tuple[Optional[int], str, Optional[str]]]:
        """`(year, reason, source)` for however this ship ended, or None.

        A Wikidata terminal event beats `fate` where both exist -- which is
        SOURCE_PRIORITY applied rather than an exception to it, so this is an
        ordinary fallback chain. It is also the better answer on the 18 ships
        that have both: the event vocabulary is controlled and already gated
        on being terminal, while `fate` sometimes holds a career event dressed
        as an outcome ("Surrendered by mutineers 1796" for a ship the timeline
        records sinking in 1801).
        """
        final = self._final_event()
        if final:
            return (int(final.date[:4]), final.description, EVENT_SOURCE)
        fate_end = self._fate_end()
        if fate_end:
            year, label = fate_end
            return (year, label, self._fate_source())
        return None

    def _fate_source(self) -> Optional[str]:
        """The highest-priority source concurring on the canonical `fate`.

        Read from `field_sources` rather than hardcoded to `dbpedia`: `fate`
        is a mergeable field, so a higher-priority source supplying it takes
        the attribution with it. None only for a `Ship` whose `fate` was
        assigned directly instead of through `set_field`.
        """
        sources = self.field_sources.get("fate", [])
        return min(sources, key=source_priority) if sources else None

    @property
    def start_year(self) -> Optional[int]:
        dated = self._dated_events()
        return int(dated[0].date[:4]) if dated else None

    @property
    def end_year(self) -> Optional[int]:
        end = self._end()
        return end[0] if end else None

    @property
    def end_reason(self) -> Optional[str]:
        end = self._end()
        return end[1] if end else None

    @property
    def end_reason_source(self) -> Optional[str]:
        """Which source `end_reason` was derived from. A controlled Wikidata
        event and a verb parsed out of an infobox fragment do not deserve
        equal confidence, and nothing else in the record tells them apart."""
        end = self._end()
        return end[2] if end else None

    def to_dict(self) -> dict:
        """The stored fields plus the derived ones.

        `asdict` serializes fields only, so the properties have to be added by
        hand -- without this they are invisible to every consumer of the
        published `ships.json`, which is most of them. All four keys are
        always present, `None` included: a key that appears for some ships and
        not others makes every consumer reach for `.get`.
        """
        data = asdict(self)
        data.update(
            start_year=self.start_year,
            end_year=self.end_year,
            end_reason=self.end_reason,
            end_reason_source=self.end_reason_source,
        )
        return data
