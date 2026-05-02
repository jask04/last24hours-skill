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
from scripts.lib import forecast, market_types, polymarket, score


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


class PolymarketEsportsQueryExpansionTests(unittest.TestCase):
    def test_named_valorant_prop_uses_domain_aware_queries(self):
        queries = polymarket._expand_queries("TenZ total kills tonight")
        self.assertEqual(queries[:5], [
            "tenz valorant kills",
            "tenz valorant kills over",
            "tenz valorant kills under",
            "tenz valorant kills map 1",
            "tenz valorant kills game 1",
        ])
        self.assertIn("tenz valorant kills kill line", queries)
        self.assertIn("tenz valorant kills more than", queries)

    def test_named_lol_prop_uses_domain_aware_queries(self):
        queries = polymarket._expand_queries("Faker solo kills tonight")
        self.assertEqual(queries[:5], [
            "faker league of legends solo kills",
            "faker league of legends solo kills over",
            "faker league of legends solo kills under",
            "faker league of legends solo kills map 1",
            "faker league of legends solo kills game 1",
        ])
        self.assertIn("faker league of legends solo kills less than", queries)
        self.assertIn("faker league of legends solo kills kill line", queries)

    def test_generic_esports_prop_watchlist_keeps_broader_query_fanout(self):
        queries = polymarket._expand_queries("Counter-Strike 2 player props today")
        self.assertIn("counter strike", queries)
        self.assertIn("cs2", queries)


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


class V1056SurfacingTests(unittest.TestCase):
    def setUp(self):
        from scripts.lib import schema
        self.prop_item = schema.PolymarketItem(
            id="PM1",
            title="donk total kills > 18.5 - Map 1",
            question="Will donk get more than 18.5 kills?",
            url="https://polymarket.com/event/cs2-donk-kills",
            market_type="esports_prop",
            relevance=0.8,
            outcome_prices=[("Yes", 0.55), ("No", 0.45)],
            spread=0.01,
            movement_24h=0.05
        )
        self.prop_item.score = 100.0
        self.prop_item.volume = 5000
        self.prop_item.liquidity = 5000
        self.prop_item.open_interest = 5000

        self.match_item = schema.PolymarketItem(
            id="PM2",
            title="CS2: NAVI vs Vitality - Match Winner",
            question="Will NAVI win?",
            url="https://polymarket.com/event/cs2-navi-vitality",
            market_type="game_outcome",
            relevance=0.8,
            outcome_prices=[("Yes", 0.60), ("No", 0.40)],
            spread=0.01,
            movement_24h=0.02
        )
        self.match_item.score = 150.0
        self.match_item.volume = 10000
        self.match_item.liquidity = 10000
        self.match_item.open_interest = 10000
        self.report = schema.Report(
            topic="",
            range_from="",
            range_to="",
            generated_at="",
            mode="quick",
            polymarket=[self.prop_item, self.match_item],
            kalshi=[]
        )

    def test_watchlist_surfaces_prop_for_prop_topic(self):
        from scripts.lib import market_watchlist
        self.report.topic = "donk kills vs Vitality tonight"
        item = market_watchlist._candidate_to_watch_item(0, self.report, self.prop_item, "Polymarket", [])
        self.assertIsNotNone(item)

    def test_watchlist_suppresses_prop_for_generic_topic(self):
        from scripts.lib import market_watchlist
        self.report.topic = "CS2 markets to watch today"
        item = market_watchlist._candidate_to_watch_item(0, self.report, self.prop_item, "Polymarket", [])
        self.assertIsNone(item)

    def test_forecast_single_market_returns_prop_for_prop_topic(self):
        from scripts.lib import forecast
        self.report.topic = "donk kills vs Vitality tonight"
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertTrue(any("donk" in (f.title or "").lower() for f in forecasts))

    def test_forecast_regression_returns_match_for_match_topic(self):
        from scripts.lib import forecast
        self.report.topic = "Counter-Strike 2 matches today"
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertTrue(any("navi" in (f.title or "").lower() for f in forecasts))
        self.assertFalse(any("donk" in (f.title or "").lower() for f in forecasts))


class ValorantAndLoLSurfacingTests(unittest.TestCase):
    def setUp(self):
        from scripts.lib import schema
        self.val_prop = schema.PolymarketItem(
            id="PM3",
            title="TenZ total kills > 18.5 - Map 1",
            question="Will TenZ get more than 18.5 kills?",
            url="https://polymarket.com/event/val-tenz-kills",
            market_type="esports_prop",
            relevance=0.8,
            outcome_prices=[("Yes", 0.55), ("No", 0.45)],
            spread=0.01,
            movement_24h=0.05
        )
        self.val_prop.score = 100.0
        self.val_prop.volume = 5000
        self.val_prop.liquidity = 5000
        self.val_prop.open_interest = 5000

        self.lol_prop = schema.PolymarketItem(
            id="PM4",
            title="Faker total kills > 4.5 - Game 1",
            question="Will Faker get more than 4.5 kills?",
            url="https://polymarket.com/event/lol-faker-kills",
            market_type="esports_prop",
            relevance=0.8,
            outcome_prices=[("Yes", 0.55), ("No", 0.45)],
            spread=0.01,
            movement_24h=0.05
        )
        self.lol_prop.score = 100.0
        self.lol_prop.volume = 5000
        self.lol_prop.liquidity = 5000
        self.lol_prop.open_interest = 5000

        self.report = schema.Report(
            topic="",
            range_from="",
            range_to="",
            generated_at="",
            mode="quick",
            polymarket=[self.val_prop, self.lol_prop],
            kalshi=[]
        )

    def test_forecast_returns_valorant_prop_for_valorant_topic(self):
        from scripts.lib import forecast
        self.report.topic = "TenZ kills vs Sentinels tonight"
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertTrue(any("tenz" in (f.title or "").lower() for f in forecasts))

    def test_forecast_returns_lol_prop_for_lol_topic(self):
        from scripts.lib import forecast
        self.report.topic = "Faker solo kills tonight"
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertTrue(any("faker" in (f.title or "").lower() for f in forecasts))

    def test_forecast_prefers_player_and_subdomain_compatible_prop(self):
        from scripts.lib import schema, forecast
        self.report.topic = "TenZ kills vs Sentinels tonight"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM5",
                title="yay total kills > 17.5 - Map 1",
                question="Will yay get more than 17.5 kills?",
                url="https://polymarket.com/event/val-yay-kills",
                market_type="esports_prop",
                relevance=0.9,
                outcome_prices=[("Yes", 0.58), ("No", 0.42)],
                spread=0.01,
                movement_24h=0.05,
            ),
            schema.PolymarketItem(
                id="PM6",
                title="TenZ total kills > 18.5 - Map 1",
                question="Will TenZ get more than 18.5 kills during the VCT match?",
                url="https://polymarket.com/event/val-tenz-kills",
                market_type="esports_prop",
                relevance=0.7,
                outcome_prices=[("Yes", 0.55), ("No", 0.45)],
                spread=0.01,
                movement_24h=0.05,
            ),
        ]
        for item in self.report.polymarket:
            item.score = 100.0
            item.volume = 5000
            item.liquidity = 5000
            item.open_interest = 5000

        forecasts = forecast.synthesize_forecasts(self.report)

        self.assertEqual(len(forecasts), 1)
        self.assertIn("tenz", forecasts[0].title.lower())

    def test_forecast_rejects_cross_title_prop_anchor(self):
        from scripts.lib import schema, forecast
        self.report.topic = "TenZ kills vs Sentinels tonight"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM7",
                title="Counter-Strike 2: donk total kills > 18.5 - Map 1",
                question="Will donk get more than 18.5 kills?",
                url="https://polymarket.com/event/cs2-donk-kills",
                market_type="esports_prop",
                relevance=0.95,
                outcome_prices=[("Yes", 0.62), ("No", 0.38)],
                spread=0.01,
                movement_24h=0.08,
            ),
        ]
        self.report.polymarket[0].score = 120.0
        self.report.polymarket[0].volume = 8000
        self.report.polymarket[0].liquidity = 8000
        self.report.polymarket[0].open_interest = 8000

        forecasts = forecast.synthesize_forecasts(self.report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")

    def test_forecast_prefers_same_day_valorant_prop_over_higher_scored_future_prop(self):
        from scripts.lib import schema, forecast
        self.report.topic = "TenZ kills vs Sentinels tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM8",
                title="TenZ total kills > 18.5 - Map 1",
                question="Will TenZ get more than 18.5 kills during the VCT match?",
                url="https://polymarket.com/event/val-tenz-kills-2026-04-24",
                market_type="esports_prop",
                relevance=0.95,
                outcome_prices=[("Yes", 0.59), ("No", 0.41)],
                spread=0.01,
                movement_24h=0.07,
                end_date="2026-04-24",
            ),
            schema.PolymarketItem(
                id="PM9",
                title="TenZ total kills > 17.5 - Map 1",
                question="Will TenZ get more than 17.5 kills during the VCT match tonight?",
                url="https://polymarket.com/event/val-tenz-kills-2026-04-22",
                market_type="esports_prop",
                relevance=0.7,
                outcome_prices=[("Yes", 0.55), ("No", 0.45)],
                spread=0.01,
                movement_24h=0.02,
                end_date="2026-04-22",
            ),
        ]
        self.report.polymarket[0].score = 140.0
        self.report.polymarket[1].score = 100.0

        forecasts = forecast.synthesize_forecasts(self.report)

        self.assertEqual(len(forecasts), 1)
        self.assertIn("2026-04-22", self.report.polymarket[1].url)
        self.assertIn("tenz", forecasts[0].title.lower())
        self.assertEqual(forecasts[0].anchor_source, "polymarket")

    def test_forecast_matches_threshold_style_valorant_prop_phrasing(self):
        from scripts.lib import schema, forecast
        self.report.topic = "TenZ total kills tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM9B",
                title="TenZ kill line - Map 1",
                question="Will TenZ record more than 17.5 kills on Map 1 in the VCT match?",
                url="https://polymarket.com/event/val-tenz-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.74,
                outcome_prices=[("Over", 0.53), ("Under", 0.47)],
                spread=0.01,
                movement_24h=0.02,
                end_date="2026-04-22",
            ),
        ]
        self.report.polymarket[0].score = 100.0
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertIn("tenz", forecasts[0].title.lower())

    def test_low_relevance_prop_candidates_can_be_preserved_for_compatibility_scoring(self):
        from scripts.lib import schema

        kept = score.relevance_filter([
            schema.PolymarketItem(
                id="PM_LOW_1",
                title="TenZ kill line - Map 1",
                question="Will TenZ record more than 17.5 kills on Map 1 tonight?",
                url="https://polymarket.com/event/val-tenz-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.18,
            ),
            schema.PolymarketItem(
                id="PM_LOW_2",
                title="yay kill line - Map 1",
                question="Will yay record more than 17.5 kills on Map 1 tonight?",
                url="https://polymarket.com/event/val-yay-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.14,
            ),
            schema.PolymarketItem(
                id="PM_LOW_3",
                title="Faker kill line - Game 1",
                question="Will Faker record more than 4.5 kills in Game 1 tonight?",
                url="https://polymarket.com/event/lol-faker-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.09,
            ),
            schema.PolymarketItem(
                id="PM_LOW_4",
                title="aspas kill line - Map 1",
                question="Will aspas record more than 16.5 kills on Map 1 tonight?",
                url="https://polymarket.com/event/val-aspas-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.04,
            ),
        ], "POLYMARKET", preserve_top_n=2)

        self.assertEqual([item.id for item in kept], ["PM_LOW_1", "PM_LOW_2"])

    def test_forecast_matches_lol_game1_prop_phrasing(self):
        from scripts.lib import schema, forecast
        self.report.topic = "Faker total kills tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM9C",
                title="Faker kill line - Game 1",
                question="Will Faker record more than 4.5 kills in Game 1 tonight?",
                url="https://polymarket.com/event/lol-faker-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.72,
                outcome_prices=[("Over", 0.54), ("Under", 0.46)],
                spread=0.01,
                movement_24h=0.03,
                end_date="2026-04-22",
            ),
        ]
        self.report.polymarket[0].score = 100.0
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertIn("faker", forecasts[0].title.lower())

    def test_named_valorant_prop_prefers_team_compatible_market_when_topic_names_team(self):
        from scripts.lib import schema, forecast
        self.report.topic = "TenZ kills vs Sentinels tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM_TEAM_OK",
                title="TenZ kill line - Map 1",
                question="Will TenZ record more than 17.5 kills for Sentinels tonight?",
                url="https://polymarket.com/event/val-tenz-sentinels-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.26,
                outcome_prices=[("Over", 0.53), ("Under", 0.47)],
                spread=0.01,
                movement_24h=0.02,
                end_date="2026-04-22",
            ),
            schema.PolymarketItem(
                id="PM_TEAM_BAD",
                title="TenZ kill line - Map 1",
                question="Will TenZ record more than 17.5 kills for another Valorant team tonight?",
                url="https://polymarket.com/event/val-tenz-other-team-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.34,
                outcome_prices=[("Over", 0.55), ("Under", 0.45)],
                spread=0.01,
                movement_24h=0.03,
                end_date="2026-04-22",
            ),
        ]
        for item in self.report.polymarket:
            item.score = 100.0

        forecasts = forecast.synthesize_forecasts(self.report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].polymarket_market_id, "PM_TEAM_OK")

    def test_forecast_keeps_solo_kills_distinct_from_generic_kills(self):
        from scripts.lib import schema, forecast
        self.report.topic = "Faker solo kills tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM9D",
                title="Faker kill line - Game 1",
                question="Will Faker record more than 4.5 kills in Game 1 tonight?",
                url="https://polymarket.com/event/lol-faker-kill-line-2026-04-22",
                market_type="esports_prop",
                relevance=0.78,
                outcome_prices=[("Over", 0.54), ("Under", 0.46)],
                spread=0.01,
                movement_24h=0.03,
                end_date="2026-04-22",
            ),
        ]
        self.report.polymarket[0].score = 120.0
        forecasts = forecast.synthesize_forecasts(self.report)
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")

    def test_named_valorant_match_prefers_compatible_game_outcome_anchor(self):
        from scripts.lib import schema, forecast
        self.report.topic = "Sentinels vs G2 tonight"
        self.report.generated_at = "2026-04-22T18:00:00+00:00"
        self.report.polymarket = [
            schema.PolymarketItem(
                id="PM10",
                title="Valorant: Karmine Corp vs FUT Esports (BO3) - VCT EMEA Group Alpha",
                question="Valorant: Karmine Corp vs FUT Esports (BO3) - VCT EMEA Group Alpha",
                url="https://polymarket.com/event/val-kc-fut-2026-04-22",
                market_type="game_outcome",
                relevance=0.96,
                outcome_prices=[("Karmine Corp", 0.62), ("FUT Esports", 0.38)],
                spread=0.01,
                movement_24h=0.03,
                end_date="2026-04-22",
            ),
            schema.PolymarketItem(
                id="PM11",
                title="Valorant: Sentinels vs G2 Esports (BO3) - VCT Americas Group Stage",
                question="Valorant: Sentinels vs G2 Esports (BO3) - VCT Americas Group Stage",
                url="https://polymarket.com/event/val-sen-g2-2026-04-22",
                market_type="game_outcome",
                relevance=0.74,
                outcome_prices=[("Sentinels", 0.57), ("G2 Esports", 0.43)],
                spread=0.01,
                movement_24h=0.04,
                end_date="2026-04-22",
            ),
        ]
        self.report.polymarket[0].score = 150.0
        self.report.polymarket[1].score = 100.0

        forecasts = forecast.synthesize_forecasts(self.report)

        self.assertEqual(len(forecasts), 1)
        self.assertIn("Sentinels vs G2", forecasts[0].title)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")


if __name__ == "__main__":
    unittest.main()
