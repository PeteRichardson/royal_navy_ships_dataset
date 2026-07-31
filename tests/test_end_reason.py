"""Tests for how Ship.end_year / Ship.end_reason are derived: the terminal-event
gating on the Wikidata timeline, and the `fate` fallback behind it."""

import unittest

from royal_navy_ships.model import (
    FATE_OUTCOMES,
    FINAL_EVENT_LABELS,
    Ship,
    ShipEvent,
    new_ship_id,
)


def ship_with(*events, fate=None, fate_source="dbpedia"):
    """A Ship whose timeline is `events`, given as (label, year-or-None).

    `fate` goes through `set_field` rather than being assigned, so
    `field_sources` is populated the way the pipeline populates it.
    """
    ship = Ship(
        id=new_ship_id(),
        events=[
            ShipEvent(description=label, date=None if year is None else f"{year}-01-01T00:00:00Z")
            for label, year in events
        ],
    )
    if fate:
        ship.set_field("fate", fate, fate_source)
    return ship


class NonTerminalTimelineTest(unittest.TestCase):
    """The reported defect: for a ship whose only dated event is its launch,
    `end_year == start_year` and `end_reason == "ship launching"`, which reads
    as though the vessel was lost at launch. 1690 of the 2190 ships with a
    dated event were in exactly this state."""

    def test_a_launch_only_ship_has_no_end(self):
        ship = ship_with(("ship launching", 1797))

        self.assertEqual(ship.start_year, 1797)
        self.assertIsNone(ship.end_year)
        self.assertIsNone(ship.end_reason)

    def test_commissioning_is_not_an_end(self):
        ship = ship_with(("ship launching", 1797), ("ship commissioning", 1798))

        self.assertIsNone(ship.end_reason)

    def test_decommissioning_is_not_an_end(self):
        """Deliberately excluded: a decommissioned hull still exists, and many
        were broken up years later. Recording it as the end would assert a
        fate the data does not state."""
        ship = ship_with(("ship launching", 1797), ("ship decommissioning", 1815))

        self.assertIsNone(ship.end_reason)

    def test_capture_is_not_an_end(self):
        """HMS Implacable was captured *into* the Royal Navy and served for
        another 144 years."""
        ship = ship_with(("ship launching", 1800), ("capture", 1805))

        self.assertIsNone(ship.end_reason)

    def test_a_ship_with_no_events_has_no_end(self):
        ship = ship_with()

        self.assertIsNone(ship.end_year)
        self.assertIsNone(ship.end_reason)


class TerminalTimelineTest(unittest.TestCase):
    def test_a_wrecked_ship_reports_its_wreck(self):
        ship = ship_with(("ship launching", 1797), ("shipwrecking", 1811))

        self.assertEqual(ship.end_year, 1811)
        self.assertEqual(ship.end_reason, "shipwrecking")

    def test_a_broken_up_ship_reports_its_breaking(self):
        ship = ship_with(("ship launching", 1797), ("ship breaking", 1850))

        self.assertEqual(ship.end_year, 1850)
        self.assertEqual(ship.end_reason, "ship breaking")

    def test_the_last_terminal_event_wins(self):
        ship = ship_with(("sinking", 1810), ("ship breaking", 1812))

        self.assertEqual(ship.end_year, 1812)
        self.assertEqual(ship.end_reason, "ship breaking")

    def test_every_terminal_label_is_recognised(self):
        for label in FINAL_EVENT_LABELS:
            with self.subTest(label=label):
                ship = ship_with(("ship launching", 1797), (label, 1850))
                self.assertEqual(ship.end_reason, label)


class LastEventDecidesTest(unittest.TestCase):
    """`end_reason` is gated on the *last* dated event, not on whether any
    terminal event appears anywhere. A non-terminal event dated after a
    terminal one means the timeline is inconsistent, and claiming an end from
    it would be asserting more than the data supports."""

    def test_a_terminal_event_followed_by_a_later_one_yields_no_end(self):
        ship = ship_with(("shipwrecking", 1811), ("transfer", 1820))

        self.assertIsNone(ship.end_reason)

    def test_undated_events_never_decide_the_end(self):
        ship = ship_with(("ship launching", 1797), ("ship breaking", None))

        self.assertIsNone(ship.end_reason)

    def test_an_undated_event_does_not_mask_a_dated_terminal_one(self):
        ship = ship_with(("name change", None), ("shipwrecking", 1811))

        self.assertEqual(ship.end_reason, "shipwrecking")


class FateFallbackTest(unittest.TestCase):
    """The Wikidata timeline records an ending for 35 ships; `fate` records one
    for about 880. A ship with no terminal event falls back to parsing `fate`."""

    def test_a_broken_up_ship_reports_its_breaking(self):
        ship = ship_with(("ship launching", 1785), fate="Broken up April 1811")

        self.assertEqual(ship.end_year, 1811)
        self.assertEqual(ship.end_reason, "ship breaking")

    def test_a_sold_ship_reports_disposal(self):
        ship = ship_with(fate="Sold January 1802")

        self.assertEqual(ship.end_year, 1802)
        self.assertEqual(ship.end_reason, "ship disposal")

    def test_the_year_need_not_follow_the_verb_immediately(self):
        ship = ship_with(fate="Sold for breaking up in 1816")

        self.assertEqual(ship.end_year, 1816)
        self.assertEqual(ship.end_reason, "ship disposal")

    def test_punctuation_after_the_verb_is_ignored(self):
        ship = ship_with(fate="Wrecked, 1809")

        self.assertEqual(ship.end_year, 1809)
        self.assertEqual(ship.end_reason, "shipwrecking")

    def test_a_hedged_date_still_yields_a_year(self):
        ship = ship_with(fate="Foundered circa November 1810")

        self.assertEqual(ship.end_year, 1810)
        self.assertEqual(ship.end_reason, "sinking")

    def test_a_twentieth_century_disposal_is_in_range(self):
        ship = ship_with(fate="Sold for scrap 1911")

        self.assertEqual(ship.end_year, 1911)

    def test_the_first_year_wins_when_several_appear(self):
        """The leading verb decides `end_reason`, so the year nearest it is the
        one that goes with it -- a later year describes what happened to the
        hulk afterwards."""
        ship = ship_with(fate="Sold 1816, hulk broken up 1823")

        self.assertEqual(ship.end_year, 1816)
        self.assertEqual(ship.end_reason, "ship disposal")

    def test_a_terminal_verb_with_no_year_still_reports_a_reason(self):
        """21 ships in the current fleet. A stated outcome with no date is
        still an answer to "how did it end"; only the year is unknown."""
        ship = ship_with(fate="Sold")

        self.assertIsNone(ship.end_year)
        self.assertEqual(ship.end_reason, "ship disposal")

    def test_every_fate_outcome_maps_into_the_wikidata_vocabulary(self):
        """`end_reason` is one vocabulary whichever source it came from, so a
        consumer can group on it. Wikidata's labels are that vocabulary."""
        for verb, label in FATE_OUTCOMES.items():
            with self.subTest(verb=verb):
                self.assertIn(label, FINAL_EVENT_LABELS)
                ship = ship_with(fate=f"{verb.capitalize()} up in 1802")
                self.assertEqual(ship.end_reason, label)


class NonTerminalFateTest(unittest.TestCase):
    """`fate` is a free-text Wikipedia infobox fragment and does not always
    hold an ending -- it frequently holds a career event instead. Only a
    recognised terminal leading verb produces an end, mirroring the gate
    `FINAL_EVENT_LABELS` applies to the event timeline."""

    def test_capture_is_not_an_end(self):
        """Same reasoning as the event timeline: a captured ship usually went
        on serving, often in the navy that took it."""
        ship = ship_with(fate="Captured by the French, 1794")

        self.assertIsNone(ship.end_year)
        self.assertIsNone(ship.end_reason)

    def test_last_listed_is_not_an_end(self):
        """"Last listed in 1808" says the records stop, not that the ship did."""
        ship = ship_with(fate="Last listed in 1808")

        self.assertIsNone(ship.end_reason)

    def test_hulking_is_not_an_end(self):
        ship = ship_with(fate="Hulked 1801")

        self.assertIsNone(ship.end_reason)

    def test_an_unrecognised_opening_yields_nothing(self):
        ship = ship_with(fate="In 1864 still in use; ultimate disposition unknown")

        self.assertIsNone(ship.end_reason)

    def test_a_terminal_verb_that_is_not_the_leading_one_is_ignored(self):
        """The leading verb is the whole grammar. "Recaptured 1776 and sold,
        possibly in 1777" opens with a career event, so nothing is claimed --
        reading the later "sold" would attach the wrong year to it."""
        ship = ship_with(fate="Recaptured 1776 and sold, possibly in 1777")

        self.assertIsNone(ship.end_reason)

    def test_a_ship_with_no_fate_has_no_end(self):
        ship = ship_with(("ship launching", 1797))

        self.assertIsNone(ship.end_year)
        self.assertIsNone(ship.end_reason)


class FatePrecedenceTest(unittest.TestCase):
    """A Wikidata terminal event beats `fate`. This is the global
    SOURCE_PRIORITY rule applied, not a per-field override: the event
    vocabulary is controlled and already gated, while `fate` sometimes holds a
    career event dressed as an outcome."""

    def test_the_terminal_event_wins_over_a_disagreeing_fate(self):
        """HMS Proselyte: the timeline records a sinking in 1801, while the
        fate string describes its 1796 surrender by mutineers -- an
        acquisition, not an ending."""
        ship = ship_with(
            ("ship launching", 1770),
            ("sinking", 1801),
            fate="Surrendered by mutineers 1796",
        )

        self.assertEqual(ship.end_year, 1801)
        self.assertEqual(ship.end_reason, "sinking")

    def test_the_terminal_event_wins_even_when_the_fate_parses(self):
        """HMS Victorious: broken up 1861 on the timeline, "Sold, 1862" in the
        infobox. Both are plausible; the controlled vocabulary decides."""
        ship = ship_with(("ship breaking", 1861), fate="Sold, 1862")

        self.assertEqual(ship.end_year, 1861)
        self.assertEqual(ship.end_reason, "ship breaking")

    def test_a_non_terminal_timeline_does_not_block_the_fate(self):
        """The gate on the event timeline says "the timeline records no
        ending", which is exactly when `fate` should be consulted."""
        ship = ship_with(
            ("ship launching", 1797),
            ("ship decommissioning", 1815),
            fate="Broken up 1820",
        )

        self.assertEqual(ship.end_year, 1820)
        self.assertEqual(ship.end_reason, "ship breaking")


class EndReasonSourceTest(unittest.TestCase):
    """A consumer cannot otherwise tell a controlled-vocabulary event from a
    parsed infobox string, and the two do not deserve equal confidence."""

    def test_an_event_derived_end_is_attributed_to_wikidata(self):
        ship = ship_with(("shipwrecking", 1811))

        self.assertEqual(ship.end_reason_source, "wikidata")

    def test_a_fate_derived_end_is_attributed_to_the_fate_source(self):
        ship = ship_with(fate="Broken up 1811")

        self.assertEqual(ship.end_reason_source, "dbpedia")

    def test_the_attribution_follows_the_source_that_won_the_fate_slot(self):
        """`fate` is a mergeable field, so it is not DBpedia's by definition --
        a higher-priority source supplying it takes the credit with it."""
        ship = ship_with(fate="Sold 1802")
        ship.set_field("fate", "Broken up 1804", "book")

        self.assertEqual(ship.end_reason, "ship breaking")
        self.assertEqual(ship.end_reason_source, "book")

    def test_a_ship_with_no_end_has_no_source(self):
        ship = ship_with(("ship launching", 1797))

        self.assertIsNone(ship.end_reason_source)


class SerializationTest(unittest.TestCase):
    """The derived properties are emitted into `ships.json`. `asdict` is
    fields-only, so `to_dict` has to add them explicitly -- before this they
    were invisible to every consumer of the published dataset."""

    def test_the_derived_fields_are_emitted(self):
        ship = ship_with(("ship launching", 1785), fate="Broken up April 1811")

        data = ship.to_dict()

        self.assertEqual(data["start_year"], 1785)
        self.assertEqual(data["end_year"], 1811)
        self.assertEqual(data["end_reason"], "ship breaking")
        self.assertEqual(data["end_reason_source"], "dbpedia")

    def test_absent_ends_are_emitted_as_null_rather_than_omitted(self):
        """A key that appears for some ships and not others forces every
        consumer to write a `.get`; the fields are always present."""
        ship = ship_with(("ship launching", 1797))

        data = ship.to_dict()

        self.assertIn("end_year", data)
        self.assertIsNone(data["end_year"])
        self.assertIsNone(data["end_reason"])
        self.assertIsNone(data["end_reason_source"])

    def test_the_stored_fields_are_still_serialized(self):
        ship = ship_with(("ship launching", 1797), fate="Broken up 1811")

        data = ship.to_dict()

        self.assertEqual(data["fate"], "Broken up 1811")
        self.assertEqual(data["field_sources"], {"fate": ["dbpedia"]})
        self.assertEqual(len(data["events"]), 1)


class StartYearUnchangedTest(unittest.TestCase):
    """`start_year` is the first dated event whatever it is, and is untouched
    by this change -- `in_sailing_era` depends on it."""

    def test_start_year_is_the_earliest_dated_event(self):
        ship = ship_with(("keel laying", 1795), ("ship launching", 1797))

        self.assertEqual(ship.start_year, 1795)

    def test_start_year_is_set_even_when_there_is_no_end(self):
        ship = ship_with(("ship launching", 1797))

        self.assertEqual(ship.start_year, 1797)
        self.assertIsNone(ship.end_year)

    def test_start_year_ignores_undated_events(self):
        ship = ship_with(("order", None), ("ship launching", 1797))

        self.assertEqual(ship.start_year, 1797)


if __name__ == "__main__":
    unittest.main()
