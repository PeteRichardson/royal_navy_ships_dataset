"""Tests for rating selection when a ship carries several rating classes."""

import itertools
import unittest

from royal_navy_ships.sources import wikidata

# The rating-class QIDs under test, by the name they map to.
QID = {name: qid for qid, name in wikidata.RATING_CLASS_QIDS.items()}


def row(ship_qid, rating, label="HMS Example", description="a ship"):
    """One row shaped like a `build_candidates_query` result binding."""
    return {
        "ship": {"value": f"http://www.wikidata.org/entity/{ship_qid}"},
        "shipLabel": {"value": label},
        "shipDescription": {"value": description},
        "class": {"value": f"http://www.wikidata.org/entity/{QID[rating]}"},
    }


def rating_from(*ratings):
    """The rating `parse_candidates` picks for one ship tagged with `ratings`."""
    rows = [row("Q1", rating) for rating in ratings]
    return wikidata.parse_candidates(rows)["Q1"]["rating"]


class RatingPriorityTest(unittest.TestCase):
    def test_rates_are_ordered_highest_first(self):
        order = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth"]
        priorities = [wikidata.rating_priority(r) for r in order]

        self.assertEqual(priorities, sorted(priorities))
        self.assertEqual(len(set(priorities)), len(order))

    def test_unrated_classes_rank_below_every_rate(self):
        self.assertLess(
            wikidata.rating_priority("Sixth"),
            wikidata.rating_priority("Sloop"),
        )
        self.assertLess(
            wikidata.rating_priority("Sloop"),
            wikidata.rating_priority("Gun-brig"),
        )

    def test_an_unknown_rating_ranks_last(self):
        self.assertGreater(
            wikidata.rating_priority(None),
            wikidata.rating_priority("Gun-brig"),
        )
        self.assertGreater(
            wikidata.rating_priority("Ironclad"),
            wikidata.rating_priority("Gun-brig"),
        )

    def test_every_mapped_class_has_a_declared_priority(self):
        """A class QID added without a priority would silently rank last and
        start winning ties it should lose."""
        for name in wikidata.RATING_CLASS_QIDS.values():
            with self.subTest(rating=name):
                self.assertIn(name, wikidata.RATING_PRIORITY)


class MultipleRatingClassesTest(unittest.TestCase):
    """About 10 ships carry more than one rating-class P31, typically
    reflecting reclassification during a career. `parse_candidates` used to
    take whichever row arrived first, which -- since rows are canonicalized by
    sorting on row JSON -- meant the lexicographically smallest class URI
    always won."""

    def test_a_rate_beats_a_gun_brig(self):
        self.assertEqual(rating_from("Third", "Gun-brig"), "Third")

    def test_gun_brig_no_longer_wins_on_sort_order(self):
        """Q130396697 (Gun-brig) sorts before every Q89xxxx rate class, so it
        used to win every one of these ties. This is the actual regression."""
        for rate in ["First", "Second", "Third", "Fourth", "Fifth", "Sixth"]:
            with self.subTest(rate=rate):
                self.assertEqual(rating_from(rate, "Gun-brig"), rate)

    def test_a_rate_beats_a_sloop(self):
        self.assertEqual(rating_from("Sixth", "Sloop"), "Sixth")

    def test_the_higher_of_two_rates_wins(self):
        self.assertEqual(rating_from("Fourth", "Second"), "Second")

    def test_sloop_beats_gun_brig(self):
        self.assertEqual(rating_from("Sloop", "Gun-brig"), "Sloop")

    def test_the_pick_does_not_depend_on_row_order(self):
        for order in itertools.permutations(["Fifth", "Sloop", "Gun-brig"]):
            with self.subTest(order=order):
                self.assertEqual(rating_from(*order), "Fifth")

    def test_three_classes_still_yield_the_highest(self):
        self.assertEqual(rating_from("Gun-brig", "Third", "Sloop"), "Third")


class UnaffectedBehaviourTest(unittest.TestCase):
    def test_a_single_class_is_used_as_is(self):
        self.assertEqual(rating_from("Fourth"), "Fourth")

    def test_one_record_per_ship_regardless_of_class_count(self):
        ships = wikidata.parse_candidates(
            [row("Q1", "Third"), row("Q1", "Gun-brig"), row("Q2", "Sloop")]
        )

        self.assertEqual(sorted(ships), ["Q1", "Q2"])

    def test_the_other_fields_survive_the_extra_rows(self):
        ships = wikidata.parse_candidates(
            [
                row("Q1", "Gun-brig", label="HMS Victory", description="a first rate"),
                row("Q1", "First", label="HMS Victory", description="a first rate"),
            ]
        )

        self.assertEqual(ships["Q1"]["label"], "HMS Victory")
        self.assertEqual(ships["Q1"]["description"], "a first rate")
        self.assertEqual(ships["Q1"]["rating"], "First")
        self.assertEqual(ships["Q1"]["events"], [])
        self.assertEqual(ships["Q1"]["guns_counts"], [])

    def test_a_missing_label_still_falls_back_to_the_qid(self):
        bare = {
            "ship": {"value": "http://www.wikidata.org/entity/Q1"},
            "class": {"value": f"http://www.wikidata.org/entity/{QID['Sloop']}"},
        }

        self.assertEqual(wikidata.parse_candidates([bare])["Q1"]["label"], "Q1")


if __name__ == "__main__":
    unittest.main()
