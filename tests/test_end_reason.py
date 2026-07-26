"""Tests for the terminal-event gating on Ship.end_year / Ship.end_reason."""

import unittest

from royal_navy_ships.model import FINAL_EVENT_LABELS, Ship, ShipEvent, new_ship_id


def ship_with(*events):
    """A Ship whose timeline is `events`, given as (label, year-or-None)."""
    return Ship(
        id=new_ship_id(),
        events=[
            ShipEvent(description=label, date=None if year is None else f"{year}-01-01T00:00:00Z")
            for label, year in events
        ],
    )


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
