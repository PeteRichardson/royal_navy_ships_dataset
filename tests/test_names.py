"""Tests for name-history reconstruction and undated naming events."""

import unittest

from royal_navy_ships.model import ShipEvent
from royal_navy_ships.sources import wikidata


def event(named_as=None, year=None, description="transfer"):
    return ShipEvent(
        description=description,
        date=None if year is None else f"{year}-01-01T00:00:00Z",
        named_as=named_as,
    )


def candidate(label, description, events):
    return {label: {"label": label, "description": description, "rating": "Third",
                    "events": events, "guns_counts": []}}


class BuildNamesTest(unittest.TestCase):
    """Unchanged behaviour: `names` is built from naming events that carry a
    date, since an undated one cannot be placed in the sequence."""

    def test_no_naming_events_falls_back_to_the_label(self):
        names = wikidata.build_names("HMS Victory", [event(description="ship launching", year=1765)])

        self.assertEqual([n.name for n in names], ["HMS Victory"])
        self.assertIsNone(names[0].start_date)

    def test_dated_naming_events_become_a_time_qualified_sequence(self):
        names = wikidata.build_names(
            "HMS Foudroyant",
            [event("Duguay-Trouin", 1800), event("HMS Implacable", 1805)],
        )

        self.assertEqual([n.name for n in names], ["Duguay-Trouin", "HMS Implacable"])
        self.assertEqual(names[0].start_date, "1800-01-01T00:00:00Z")
        self.assertEqual(names[0].end_date, "1805-01-01T00:00:00Z")
        self.assertIsNone(names[1].end_date)

    def test_an_undated_naming_event_does_not_enter_the_sequence(self):
        """Its position is unknowable, and `current_name` returns names[-1] --
        an arbitrarily placed entry would make that arbitrary too."""
        names = wikidata.build_names(
            "HMS Recovery",
            [event("HMS Recovery", 1781), event("Minerve", None)],
        )

        self.assertEqual([n.name for n in names], ["HMS Recovery"])


class UndatedNamesTest(unittest.TestCase):
    def test_an_undated_naming_event_is_collected(self):
        self.assertEqual(wikidata.undated_names([event("Minerve", None)]), ["Minerve"])

    def test_dated_naming_events_are_not_collected(self):
        self.assertEqual(wikidata.undated_names([event("Minerve", 1778)]), [])

    def test_events_without_a_name_are_ignored(self):
        self.assertEqual(wikidata.undated_names([event(None, None)]), [])

    def test_duplicates_are_collapsed_in_first_seen_order(self):
        events = [event("Minerve", None), event("Actif", None), event("Minerve", None)]

        self.assertEqual(wikidata.undated_names(events), ["Minerve", "Actif"])


class BuildNotesTest(unittest.TestCase):
    """#13's decision: an undated former name is recorded in `notes` rather
    than appended to `names`, so nothing is silently lost and the name
    sequence stays trustworthy."""

    def test_the_description_is_unchanged_when_there_is_nothing_to_add(self):
        notes = wikidata.build_notes("A third-rate ship of the line.", [], {"HMS Victory"})

        self.assertEqual(notes, "A third-rate ship of the line.")

    def test_an_undated_name_is_recorded(self):
        notes = wikidata.build_notes(
            "A fifth-rate frigate.", [event("Minerve", None)], {"HMS Recovery"}
        )

        self.assertIn("Minerve", notes)
        self.assertTrue(notes.startswith("A fifth-rate frigate."))

    def test_several_undated_names_are_all_recorded(self):
        notes = wikidata.build_notes(
            "", [event("Minerve", None), event("Actif", None)], set()
        )

        self.assertIn("Minerve", notes)
        self.assertIn("Actif", notes)

    def test_a_name_already_in_the_sequence_is_not_repeated(self):
        notes = wikidata.build_notes(
            "A frigate.", [event("HMS Recovery", None)], {"HMS Recovery"}
        )

        self.assertEqual(notes, "A frigate.")

    def test_an_empty_description_yields_no_leading_whitespace(self):
        notes = wikidata.build_notes("", [event("Minerve", None)], set())

        self.assertEqual(notes, notes.strip())
        self.assertTrue(notes)

    def test_the_note_says_the_date_is_missing(self):
        """A reader must be able to tell this is a data gap, not a claim about
        ordering."""
        notes = wikidata.build_notes("", [event("Minerve", None)], set())

        self.assertIn("no date", notes.lower())


class ToShipsIntegrationTest(unittest.TestCase):
    def test_an_undated_name_survives_into_the_ship_record(self):
        ships = wikidata.to_ships(
            candidate(
                "HMS Recovery",
                "A fifth-rate frigate.",
                [event("HMS Recovery", 1781), event("Minerve", None)],
            )
        )
        ship = ships[0]

        self.assertEqual([n.name for n in ship.names], ["HMS Recovery"])
        self.assertIn("Minerve", ship.notes)

    def test_a_ship_with_no_undated_names_is_unaffected(self):
        ships = wikidata.to_ships(
            candidate("HMS Victory", "A first-rate.", [event("HMS Victory", 1765)])
        )

        self.assertEqual(ships[0].notes, "A first-rate.")


if __name__ == "__main__":
    unittest.main()
