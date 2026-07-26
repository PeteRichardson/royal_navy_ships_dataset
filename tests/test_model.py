"""Tests for the canonical Ship model's field-merge policy."""

import itertools
import unittest

from royal_navy_ships.model import Ship, new_ship_id


def make_ship():
    return Ship(id=new_ship_id())


def conflict_set(ship, name):
    """The ship's conflicts for `name` as an order-insensitive set."""
    return {(e["value"], e["source"]) for e in ship.conflicts.get(name, [])}


class FirstValueTest(unittest.TestCase):
    def test_first_non_empty_value_takes_the_canonical_slot(self):
        ship = make_ship()

        ship.set_field("builder", "Chatham", "wikidata")

        self.assertEqual(ship.builder, "Chatham")
        self.assertEqual(ship.field_sources["builder"], ["wikidata"])
        self.assertEqual(ship.conflicts, {})

    def test_empty_values_are_ignored(self):
        ship = make_ship()

        ship.set_field("builder", None, "wikidata")
        ship.set_field("builder", "", "dbpedia")

        self.assertIsNone(ship.builder)
        self.assertEqual(ship.field_sources, {})

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            make_ship().set_field("draught", "12", "dbpedia")


class AgreementTest(unittest.TestCase):
    """#19: a source repeating the canonical value is corroboration, and the
    fact that it corroborated has to survive into the output -- otherwise a
    source that both agrees and offers an alternative is indistinguishable
    from one that only disagrees."""

    def test_agreeing_source_is_recorded(self):
        ship = make_ship()

        ship.set_field("builder", "Chatham", "wikidata")
        ship.set_field("builder", "Chatham", "dbpedia")

        self.assertEqual(ship.builder, "Chatham")
        self.assertEqual(ship.field_sources["builder"], ["wikidata", "dbpedia"])
        self.assertEqual(ship.conflicts, {})

    def test_agreement_is_not_recorded_twice(self):
        ship = make_ship()

        ship.set_field("builder", "Chatham", "wikidata")
        ship.set_field("builder", "Chatham", "dbpedia")
        ship.set_field("builder", "Chatham", "dbpedia")

        self.assertEqual(ship.field_sources["builder"], ["wikidata", "dbpedia"])

    def test_same_source_alternative_is_distinguishable_from_disagreement(self):
        """The X/Y collision from #19, which used to serialize identically."""
        # Ship X -- a real cross-source disagreement.
        x = make_ship()
        x.set_field("builder", "Chatham", "wikidata")
        x.set_field("builder", "Woolwich", "dbpedia")

        # Ship Y -- DBpedia corroborates *and* offers an extra value.
        y = make_ship()
        y.set_field("builder", "Chatham", "wikidata")
        y.set_field("builder", "Chatham", "dbpedia")
        y.set_field("builder", "Woolwich", "dbpedia")

        # Both hold the same canonical answer and the same conflict entry...
        self.assertEqual(x.builder, y.builder)
        self.assertEqual(conflict_set(x, "builder"), conflict_set(y, "builder"))

        # ...and are now told apart by whether the conflict's source concurred.
        self.assertNotIn("dbpedia", x.field_sources["builder"])
        self.assertIn("dbpedia", y.field_sources["builder"])


class PrecedenceTest(unittest.TestCase):
    """#18: precedence is a declared policy, not the order pipeline.main()
    happens to call the adapters in."""

    def test_lower_priority_source_cannot_displace(self):
        ship = make_ship()

        ship.set_field("guns", "74", "wikidata")
        ship.set_field("guns", "80", "dbpedia")

        self.assertEqual(ship.guns, "74")
        self.assertEqual(ship.field_sources["guns"], ["wikidata"])
        self.assertEqual(conflict_set(ship, "guns"), {("80", "dbpedia")})

    def test_higher_priority_source_displaces_and_demotes_the_incumbent(self):
        ship = make_ship()

        ship.set_field("guns", "74", "wikidata")
        ship.set_field("guns", "80", "book")

        self.assertEqual(ship.guns, "80")
        self.assertEqual(ship.field_sources["guns"], ["book"])
        self.assertEqual(conflict_set(ship, "guns"), {("74", "wikidata")})

    def test_displacement_demotes_every_concurring_source(self):
        ship = make_ship()

        ship.set_field("guns", "74", "wikidata")
        ship.set_field("guns", "74", "dbpedia")
        ship.set_field("guns", "80", "book")

        self.assertEqual(ship.guns, "80")
        self.assertEqual(ship.field_sources["guns"], ["book"])
        self.assertEqual(
            conflict_set(ship, "guns"),
            {("74", "wikidata"), ("74", "dbpedia")},
        )

    def test_equal_priority_disagreement_keeps_the_incumbent(self):
        """DBpedia emitting several values for one infobox field -- the only
        case that actually occurs in the current dataset."""
        ship = make_ship()

        ship.set_field("builder", "Chatham", "dbpedia")
        ship.set_field("builder", "Woolwich", "dbpedia")

        self.assertEqual(ship.builder, "Chatham")
        self.assertEqual(conflict_set(ship, "builder"), {("Woolwich", "dbpedia")})

    def test_identical_conflict_is_not_recorded_twice(self):
        ship = make_ship()

        ship.set_field("builder", "Chatham", "wikidata")
        ship.set_field("builder", "Woolwich", "dbpedia")
        ship.set_field("builder", "Woolwich", "dbpedia")

        self.assertEqual(len(ship.conflicts["builder"]), 1)

    def test_unknown_source_ranks_below_every_declared_one(self):
        ship = make_ship()

        ship.set_field("guns", "74", "dbpedia")
        ship.set_field("guns", "80", "some-new-adapter")

        self.assertEqual(ship.guns, "74")

    def test_promotion_reclaims_a_conflict_that_agrees_with_the_new_value(self):
        """Once `80` becomes canonical, DBpedia's `80` is corroboration -- it
        must not stay in `conflicts` describing a disagreement with itself."""
        ship = make_ship()

        ship.set_field("guns", "74", "wikidata")
        ship.set_field("guns", "80", "dbpedia")
        ship.set_field("guns", "80", "book")

        self.assertEqual(ship.guns, "80")
        self.assertEqual(ship.field_sources["guns"], ["book", "dbpedia"])
        self.assertEqual(conflict_set(ship, "guns"), {("74", "wikidata")})


class OrderIndependenceTest(unittest.TestCase):
    """#18's headline acceptance criterion: running the adapters in any order
    produces the same canonical values."""

    VALUES = [("wikidata", "74"), ("dbpedia", "80"), ("book", "76")]

    def test_canonical_value_is_the_same_in_every_call_order(self):
        results = []
        for order in itertools.permutations(self.VALUES):
            ship = make_ship()
            for source, value in order:
                ship.set_field("guns", value, source)
            results.append((ship.guns, ship.field_sources["guns"], conflict_set(ship, "guns")))

        canonical = {r[0] for r in results}
        sources = {tuple(r[1]) for r in results}
        conflicts = {frozenset(r[2]) for r in results}

        self.assertEqual(canonical, {"76"})  # book wins outright
        self.assertEqual(sources, {("book",)})
        self.assertEqual(
            conflicts,
            {frozenset({("74", "wikidata"), ("80", "dbpedia")})},
        )

    def test_no_conflict_ever_duplicates_the_canonical_value(self):
        for order in itertools.permutations(self.VALUES):
            ship = make_ship()
            for source, value in order:
                ship.set_field("guns", value, source)
            with self.subTest(order=[s for s, _ in order]):
                self.assertNotIn(
                    ship.guns,
                    [e["value"] for e in ship.conflicts.get("guns", [])],
                )


class ExistingBehaviourTest(unittest.TestCase):
    """#18: no existing behaviour changes while only Wikidata and DBpedia are
    wired up -- Wikidata already outranks DBpedia, which is what call order
    was accidentally delivering."""

    def test_wikidata_still_beats_dbpedia_in_either_call_order(self):
        forwards = make_ship()
        forwards.set_field("guns", "74", "wikidata")
        forwards.set_field("guns", "80", "dbpedia")

        backwards = make_ship()
        backwards.set_field("guns", "80", "dbpedia")
        backwards.set_field("guns", "74", "wikidata")

        self.assertEqual(forwards.guns, "74")
        self.assertEqual(backwards.guns, "74")


if __name__ == "__main__":
    unittest.main()
