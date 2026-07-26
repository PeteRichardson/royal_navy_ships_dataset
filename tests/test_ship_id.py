"""Tests for stable, reproducible ship identifiers."""

import unittest
import uuid

from royal_navy_ships.model import SHIP_ID_NAMESPACE, new_ship_id, ship_id
from royal_navy_ships.sources import wikidata


def candidate(label="HMS Victory", rating="First"):
    """One entry shaped like a `parse_candidates` result value."""
    return {
        "label": label,
        "description": "",
        "rating": rating,
        "events": [],
        "guns_counts": [],
    }


class ShipIdTest(unittest.TestCase):
    def test_the_same_qid_always_yields_the_same_id(self):
        self.assertEqual(
            ship_id({"wikidata": "Q213958"}),
            ship_id({"wikidata": "Q213958"}),
        )

    def test_different_qids_yield_different_ids(self):
        self.assertNotEqual(
            ship_id({"wikidata": "Q213958"}),
            ship_id({"wikidata": "Q63218"}),
        )

    def test_the_id_is_a_uuid_string(self):
        value = ship_id({"wikidata": "Q213958"})

        self.assertEqual(str(uuid.UUID(value)), value)

    def test_the_identifier_system_is_part_of_the_key(self):
        """Two systems that happen to issue the same identifier string must not
        collide -- the id is derived from `system:value`, not from `value`."""
        self.assertNotEqual(
            ship_id({"wikidata": "Victory"}),
            ship_id({"dbpedia": "Victory"}),
        )

    def test_wikidata_wins_when_several_identifiers_are_present(self):
        with_both = ship_id({"wikidata": "Q213958", "dbpedia": "HMS_Victory"})

        self.assertEqual(with_both, ship_id({"wikidata": "Q213958"}))

    def test_a_ship_with_no_known_identifier_gets_a_random_id(self):
        first = ship_id({})
        second = ship_id({})

        self.assertNotEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)

    def test_an_empty_identifier_value_is_not_used(self):
        self.assertNotEqual(ship_id({"wikidata": ""}), ship_id({"wikidata": ""}))

    def test_new_ship_id_is_still_random(self):
        self.assertNotEqual(new_ship_id(), new_ship_id())


class IdStabilityPinTest(unittest.TestCase):
    """These literals are the dataset's published ids. A refactor that changes
    the derivation renumbers every ship in every consumer's join -- which is
    exactly the failure #14 exists to prevent -- so pin them rather than
    recompute them from the code under test."""

    def test_namespace_is_pinned(self):
        self.assertEqual(str(SHIP_ID_NAMESPACE), "41714beb-335c-5c64-b798-3329efefc252")

    def test_hms_victory_id_is_pinned(self):
        self.assertEqual(
            ship_id({"wikidata": "Q213958"}),
            "decdbb0b-bd2f-509c-8b7d-7fcf6c73d7b0",
        )


class AdapterStabilityTest(unittest.TestCase):
    def test_two_runs_of_the_adapter_produce_the_same_ids(self):
        first = wikidata.to_ships({"Q213958": candidate()})
        second = wikidata.to_ships({"Q213958": candidate()})

        self.assertEqual(first[0].id, second[0].id)

    def test_the_id_survives_a_relabelled_ship(self):
        """Renaming on Wikidata must not renumber the record."""
        first = wikidata.to_ships({"Q63218": candidate(label="HMS Implacable")})
        second = wikidata.to_ships({"Q63218": candidate(label="HMS Foudroyant")})

        self.assertEqual(first[0].id, second[0].id)

    def test_distinct_ships_still_get_distinct_ids(self):
        ships = wikidata.to_ships({"Q213958": candidate(), "Q63218": candidate()})

        self.assertEqual(len({s.id for s in ships}), 2)


if __name__ == "__main__":
    unittest.main()
