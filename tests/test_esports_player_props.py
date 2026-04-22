"""Detection-only tests for the CS2/Valorant/LoL player-prop groundwork (v1.0.55).

v1.0.55 ships classifiers + rosters + market-type markers. No surfacing wiring
yet — that lands in v1.0.56. These tests assert:
  * Curated CS2/Valorant/LoL rosters extract correctly
  * `is_esports_player_prop_query` distinguishes player-prop queries from
    match-level slate queries
  * Existing `_is_esports_match_query` continues to reject player-prop queries
    so match-slate and player-prop paths stay disjoint
  * `market_types.classify_market` tags player-prop titles as `esports_prop`
"""

import unittest

from scripts.lib import evidence_quality as eq
from scripts.lib import forecast, market_types


class CS2PlayerRosterTests(unittest.TestCase):
    def test_is_cs2_player_text_positive(self):
        self.assertTrue(eq.is_cs2_player_text("donk kills vs Vitality"))
        self.assertTrue(eq.is_cs2_player_text("s1mple and ZywOo rating"))
        self.assertTrue(eq.is_cs2_player_text("NiKo headshot total tonight"))

    def test_extract_cs2_players_lowercases(self):
        self.assertEqual(
            eq.extract_cs2_players("S1mple and ZywOo headshots"),
            {"s1mple", "zywoo"},
        )

    def test_extract_cs2_players_no_match(self):
        self.assertEqual(eq.extract_cs2_players("Lakers at Warriors tonight"), set())

    def test_non_cs2_player_not_in_cs2_roster(self):
        # Faker is an LoL player, not CS2 — CS2-scoped lookup should miss.
        self.assertEqual(eq.extract_cs2_players("Faker solo kills"), set())
        self.assertIn("faker", eq.extract_esports_players("Faker solo kills"))


class ValorantAndLoLRosterTests(unittest.TestCase):
    def test_valorant_roster_lookup(self):
        players = eq.extract_esports_players("TenZ vs Sentinels tonight", subdomain="valorant")
        self.assertEqual(players, {"tenz"})

    def test_lol_roster_lookup(self):
        players = eq.extract_esports_players("Faker solo kills", subdomain="lol")
        self.assertEqual(players, {"faker"})

    def test_aggregate_roster_crosses_subdomains(self):
        text = "donk and TenZ and Faker"
        players = eq.extract_esports_players(text)
        self.assertEqual(players, {"donk", "tenz", "faker"})

    def test_cs2_subdomain_isolates_cs2_players(self):
        # TenZ should not appear in CS2-scoped lookup
        self.assertEqual(
            eq.extract_esports_players("TenZ kills vs Sentinels", subdomain="cs2"),
            set(),
        )


class PlayerPropQueryClassifierTests(unittest.TestCase):
    def test_player_name_triggers_prop_query(self):
        self.assertTrue(eq.is_esports_player_prop_query("donk kills vs Vitality tonight"))
        self.assertTrue(eq.is_esports_player_prop_query("s1mple headshots tonight"))
        self.assertTrue(eq.is_esports_player_prop_query("TenZ kills vs Sentinels"))
        self.assertTrue(eq.is_esports_player_prop_query("Faker solo kills"))

    def test_stat_marker_plus_esports_term_triggers(self):
        self.assertTrue(eq.is_esports_player_prop_query("CS2 total kills over/under tonight"))
        self.assertTrue(eq.is_esports_player_prop_query("Valorant ADR props tonight"))

    def test_match_slate_query_is_not_prop(self):
        self.assertFalse(eq.is_esports_player_prop_query("Counter-Strike 2 matches today"))
        self.assertFalse(eq.is_esports_player_prop_query("CS2 tournaments this week"))
        self.assertFalse(eq.is_esports_player_prop_query("Valorant matches tomorrow"))

    def test_non_esports_query_is_not_prop(self):
        self.assertFalse(eq.is_esports_player_prop_query("Lakers at Warriors tonight"))
        self.assertFalse(eq.is_esports_player_prop_query("donk the dictator"))  # no esports context

    def test_empty_query(self):
        self.assertFalse(eq.is_esports_player_prop_query(""))
        self.assertFalse(eq.is_esports_player_prop_query(None))


class MatchAndPropPathsAreDisjointTests(unittest.TestCase):
    def test_match_query_rejects_kills(self):
        # Existing guard: kills/props/handicap disqualify from match classification.
        self.assertFalse(forecast._is_esports_match_query("donk kills vs Vitality tonight"))

    def test_match_query_accepts_match_slate(self):
        self.assertTrue(forecast._is_esports_match_query("Counter-Strike 2 matches today"))

    def test_forecast_wrapper_matches_eq_helper(self):
        # forecast._is_esports_player_prop_query is a thin wrapper on eq.
        self.assertTrue(forecast._is_esports_player_prop_query("donk kills vs Vitality"))
        self.assertFalse(forecast._is_esports_player_prop_query("Counter-Strike 2 matches today"))


class MarketTypeClassificationTests(unittest.TestCase):
    def test_player_prop_title_classified_as_esports_prop(self):
        mt = market_types.classify_market(
            title="donk total kills - Map 1",
            question="Will donk record 18.5 or more kills on Map 1 vs Vitality?",
            url="https://polymarket.com/event/cs2-donk-total-kills-map-1",
        )
        self.assertEqual(mt, "esports_prop")

    def test_headshot_prop_classified_as_esports_prop(self):
        mt = market_types.classify_market(
            title="s1mple headshots - Map 2",
            question="s1mple headshot total Map 2 vs FaZe",
            url="",
        )
        self.assertEqual(mt, "esports_prop")

    def test_match_winner_still_game_outcome(self):
        # classify_market requires an eSports keyword (cs2/csgo/valorant/etc.) in
        # text to tag a matchup as eSports game_outcome — team names alone are
        # not enough. Include CS2 in the title to anchor the classification.
        mt = market_types.classify_market(
            title="CS2: NAVI vs Vitality - Match Winner (BO3)",
            question="Will NAVI win the BO3 match?",
            url="https://polymarket.com/event/cs2-navi-vs-vitality",
        )
        self.assertEqual(mt, "game_outcome")


class StatMarkerHelperTests(unittest.TestCase):
    def test_kills_marker(self):
        self.assertTrue(eq.has_player_prop_stat_marker("total kills over/under"))

    def test_first_blood_phrase(self):
        self.assertTrue(eq.has_player_prop_stat_marker("first blood probability"))

    def test_clutch_marker(self):
        self.assertTrue(eq.has_player_prop_stat_marker("1v1 clutch attempts"))

    def test_no_stat_marker(self):
        self.assertFalse(eq.has_player_prop_stat_marker("match winner prediction"))


if __name__ == "__main__":
    unittest.main()
