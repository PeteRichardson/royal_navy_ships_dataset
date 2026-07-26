"""Tests for the Wikidata source adapter."""

import unittest

from royal_navy_ships.model import Ship, ShipEvent, new_ship_id
from royal_navy_ships.sources import wikidata


def make_ship(rating, years=()):
    """A Ship with `rating` and one launch event per year in `years`."""
    ship = Ship(id=new_ship_id())
    ship.set_field("rating", rating, "wikidata")
    ship.events = [
        ShipEvent(description="ship launching", date=f"{year}-01-01T00:00:00Z")
        for year in years
    ]
    return ship


def binding(ship_qid, date_value):
    """One row shaped like a `build_events_query` result binding."""
    row = {
        "ship": {"value": f"http://www.wikidata.org/entity/{ship_qid}"},
        "eventLabel": {"value": "ship launching"},
    }
    if date_value is not None:
        row["date"] = {"value": date_value}
    return row


class UnknownValueDatesTest(unittest.TestCase):
    """Wikidata serializes a `somevalue` P585 qualifier as a skolem IRI, not a
    date. It must not reach the model as one -- `Ship.start_year` parses the
    first four characters of every event date as an integer."""

    def test_unknown_value_date_is_recorded_as_no_date(self):
        ships = {"Q1": {"events": []}}
        genid = "http://www.wikidata.org/.well-known/genid/55a359633f2bb2cf"

        wikidata.attach_events(ships, [binding("Q1", genid)])

        self.assertEqual(len(ships["Q1"]["events"]), 1)
        self.assertIsNone(ships["Q1"]["events"][0].date)

    def test_real_date_is_preserved(self):
        ships = {"Q1": {"events": []}}

        wikidata.attach_events(ships, [binding("Q1", "1797-04-12T00:00:00Z")])

        self.assertEqual(ships["Q1"]["events"][0].date, "1797-04-12T00:00:00Z")

    def test_start_year_survives_an_unknown_value_date(self):
        ships = {"Q1": {"events": []}}
        genid = "http://www.wikidata.org/.well-known/genid/55a359633f2bb2cf"

        wikidata.attach_events(ships, [binding("Q1", genid)])
        ship = Ship(id=new_ship_id(), events=ships["Q1"]["events"])

        self.assertIsNone(ship.start_year)


class SailingEraFilterTest(unittest.TestCase):
    """`sloop-of-war` (Q928235) is not era-bounded on Wikidata: the same class
    covers 1790s sailing sloops and 1915 Acacia-class convoy escorts. The rated
    classes are era-bounded by the rating system itself and are never filtered."""

    def test_sloop_launched_before_the_cutoff_is_kept(self):
        self.assertTrue(wikidata.in_sailing_era(make_ship("Sloop", [1797])))

    def test_sloop_launched_after_the_cutoff_is_dropped(self):
        self.assertFalse(wikidata.in_sailing_era(make_ship("Sloop", [1915])))

    def test_gun_brig_launched_after_the_cutoff_is_dropped(self):
        self.assertFalse(wikidata.in_sailing_era(make_ship("Gun-brig", [2011])))

    def test_ship_launched_in_the_cutoff_year_is_dropped(self):
        self.assertFalse(wikidata.in_sailing_era(make_ship("Sloop", [1860])))

    def test_undated_sloop_is_kept(self):
        self.assertTrue(wikidata.in_sailing_era(make_ship("Sloop", [])))

    def test_rated_ship_after_the_cutoff_is_kept(self):
        # HMS Heroine, an 1881 fifth-rate, is the real record this protects.
        self.assertTrue(wikidata.in_sailing_era(make_ship("Fifth", [1881])))

    def test_ship_with_no_rating_is_kept(self):
        self.assertTrue(wikidata.in_sailing_era(make_ship(None, [1915])))

    def test_earliest_event_decides_not_the_latest(self):
        # A sailing sloop wrecked long after launch stays in; the launch is what
        # dates the vessel.
        self.assertTrue(wikidata.in_sailing_era(make_ship("Sloop", [1804, 1889])))


if __name__ == "__main__":
    unittest.main()
