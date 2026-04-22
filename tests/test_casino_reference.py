"""Regression tests for the static casino-game reference table (v1.0.54)."""

import unittest

from scripts.lib import casino_reference


class LookupCasinoContextTests(unittest.TestCase):
    def test_american_roulette_specific(self):
        rows = casino_reference.lookup_casino_context("house edge on American roulette")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "roulette_american")
        self.assertAlmostEqual(rows[0]["house_edge"], 0.0526, places=4)

    def test_european_roulette_specific(self):
        rows = casino_reference.lookup_casino_context("European roulette RTP")
        self.assertEqual(rows[0]["key"], "roulette_european")
        self.assertAlmostEqual(rows[0]["house_edge"], 0.027, places=4)

    def test_bare_roulette_defaults_to_american(self):
        rows = casino_reference.lookup_casino_context("roulette odds")
        self.assertEqual(rows[0]["key"], "roulette_american")

    def test_blackjack_match(self):
        rows = casino_reference.lookup_casino_context("blackjack basic strategy edge")
        self.assertEqual(rows[0]["key"], "blackjack")
        self.assertTrue(0.0 < rows[0]["house_edge"] < 0.02)

    def test_baccarat_match(self):
        rows = casino_reference.lookup_casino_context("baccarat banker bet")
        self.assertEqual(rows[0]["key"], "baccarat_banker")

    def test_craps_match(self):
        rows = casino_reference.lookup_casino_context("craps pass line edge")
        self.assertEqual(rows[0]["key"], "craps_pass_line")

    def test_video_poker_match(self):
        rows = casino_reference.lookup_casino_context("9/6 Jacks or Better RTP")
        self.assertEqual(rows[0]["key"], "video_poker_jacks_or_better")

    def test_slots_match(self):
        rows = casino_reference.lookup_casino_context("typical Vegas Strip slots RTP")
        self.assertEqual(rows[0]["key"], "slots_typical")

    def test_no_match_returns_empty(self):
        self.assertEqual(casino_reference.lookup_casino_context("Lakers at Warriors"), [])
        self.assertEqual(casino_reference.lookup_casino_context(""), [])

    def test_is_casino_query_matches_positive(self):
        self.assertTrue(casino_reference.is_casino_query("blackjack edge"))
        self.assertFalse(casino_reference.is_casino_query("nba game tonight"))

    def test_21_in_non_casino_context_does_not_match(self):
        # "21 savage", "21 Jump Street", "21 pilots" should not trip blackjack
        self.assertEqual(casino_reference.lookup_casino_context("21 savage new album"), [])
        self.assertEqual(casino_reference.lookup_casino_context("21 pilots tour"), [])

    def test_multiple_games_in_one_topic(self):
        rows = casino_reference.lookup_casino_context("blackjack vs baccarat house edge")
        keys = {r["key"] for r in rows}
        self.assertEqual(keys, {"blackjack", "baccarat_banker"})


class BuildReferenceItemTests(unittest.TestCase):
    def test_build_reference_item_shape(self):
        item = casino_reference.build_reference_item("blackjack", topic="blackjack edge")
        self.assertEqual(item["kind"], "casino_reference")
        self.assertEqual(item["game"], "Blackjack")
        self.assertIn("house_edge", item)
        self.assertIn("edge_range", item)
        self.assertIn("rtp", item)
        self.assertIn("notes", item)
        self.assertEqual(item["topic"], "blackjack edge")

    def test_unknown_key_returns_empty(self):
        self.assertEqual(casino_reference.build_reference_item("not_a_game"), {})


class AvailableKeysTests(unittest.TestCase):
    def test_available_keys_stable(self):
        keys = casino_reference.available_keys()
        self.assertIn("blackjack", keys)
        self.assertIn("roulette_american", keys)
        self.assertIn("baccarat_banker", keys)
        # Sorted output
        self.assertEqual(keys, sorted(keys))


if __name__ == "__main__":
    unittest.main()
