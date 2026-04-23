import unittest
from unittest import mock

from scripts.lib import evidence_fusion, forecast, market_watchlist, render, schema, sports_schedule


def _report(topic: str) -> schema.Report:
    return schema.Report(
        topic=topic,
        range_from="2026-04-20",
        range_to="2026-04-21",
        generated_at="2026-04-21T00:00:00+00:00",
        mode="both",
    )


def _engagement(volume=1_000_000, liquidity=250_000, open_interest=None):
    return schema.Engagement(volume=volume, liquidity=liquidity, open_interest=open_interest)


class ForecastWatchlistTests(unittest.TestCase):
    def test_nba_date_window_counts_as_slate_query(self):
        self.assertTrue(sports_schedule.is_nba_slate_query("NBA matchups April 21 through April 23"))

    def test_cs2_watchlist_search_topics_include_counter_strike_alias(self):
        topics = market_watchlist.search_topics("Counter-Strike 2 markets to watch today")
        self.assertIn("counter strike", topics)

    def test_nba_slate_render_shows_only_direct_game_markets(self):
        report = _report("NBA matchups April 21 through April 23")
        report.forecasts = [
            schema.ForecastItem(
                title="76ers vs. Celtics",
                forecast_probability=0.88,
                forecast_range_low=0.84,
                forecast_range_high=0.92,
                favorite_label="Celtics",
                polymarket_market_id="PM1",
                anchor_source="polymarket",
                market_view="Polymarket 88%",
                why_line="Mostly market-driven right now.",
                confidence_level="moderate-low",
                uncertainty="Confidence is moderate-low.",
            ),
            schema.ForecastItem(
                title="Magic vs. Pistons",
                forecast_probability=0.78,
                forecast_range_low=0.74,
                forecast_range_high=0.82,
                favorite_label="Pistons",
                polymarket_market_id="PM4",
                anchor_source="polymarket",
                market_view="Polymarket 78%",
                why_line="Mostly market-driven right now.",
                confidence_level="moderate-low",
                uncertainty="Confidence is moderate-low.",
            ),
        ]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="76ers vs. Celtics",
                question="76ers vs. Celtics",
                url="https://polymarket.com/event/nba-phi-bos-2026-04-21",
                outcome_prices=[("76ers", 0.12), ("Celtics", 0.88)],
                engagement=_engagement(),
                market_type="game_outcome",
                relevance=0.95,
                score=95,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Spread: Rockets (-4.5)",
                question="Rockets vs. Lakers",
                url="https://polymarket.com/event/nba-hou-lal-2026-04-21",
                outcome_prices=[("Rockets", 0.52), ("Lakers", 0.48)],
                engagement=_engagement(),
                market_type="team_prop",
                relevance=0.9,
                score=90,
            ),
            schema.PolymarketItem(
                id="PM3",
                title="NBA Playoffs: Who Will Win Series? - 76ers vs. Celtics",
                question="NBA Playoffs: Who Will Win Series? - 76ers vs. Celtics",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-76ers-vs-celtics",
                outcome_prices=[("76ers", 0.04), ("Celtics", 0.96)],
                engagement=_engagement(),
                market_type="futures",
                relevance=0.9,
                score=90,
            ),
            schema.PolymarketItem(
                id="PM4",
                title="Magic vs. Pistons",
                question="Magic vs. Pistons",
                url="https://polymarket.com/event/nba-orl-det-2026-04-22",
                outcome_prices=[("Magic", 0.22), ("Pistons", 0.78)],
                engagement=_engagement(),
                market_type="game_outcome",
                relevance=0.95,
                score=93,
            ),
        ]

        output = render.render_compact(report)

        self.assertIn("76ers vs. Celtics", output)
        self.assertNotIn("Spread: Rockets (-4.5)", output)
        self.assertNotIn("Who Will Win Series", output)

    def test_nba_slate_x_section_filters_how_to_watch_and_ats_copy(self):
        report = _report("NBA matchups April 21 through April 23")
        report.forecasts = [
            schema.ForecastItem(
                title="Trail Blazers vs. Spurs",
                forecast_probability=0.86,
                forecast_range_low=0.82,
                forecast_range_high=0.90,
                favorite_label="Spurs",
                polymarket_market_id="PM1",
                anchor_source="polymarket",
                market_view="Polymarket 86%",
                why_line="Mostly market-driven right now.",
                confidence_level="moderate-low",
                uncertainty="Confidence is moderate-low.",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="How to watch Portland Trail Blazers-San Antonio Spurs, Game 2: TV, live stream for Tuesday's NBA playoff game.",
                url="https://x.com/media/status/1",
                author_handle="AzspNews",
                score=84,
            ),
            schema.XItem(
                id="X2",
                text="NBA Playoffs: Portland Trail Blazers vs. San Antonio Spurs (Game 2) Line: San Antonio -11.5 | Total: 220.0 The ATS Angle San Antonio must maintain defensive dominance to cover.",
                url="https://x.com/edge/status/2",
                author_handle="TheEdgeAnalyst",
                score=87,
            ),
        ]

        output = render.render_compact(report)

        self.assertNotIn("How to watch Portland Trail Blazers-San Antonio Spurs", output)
        self.assertNotIn("The ATS Angle", output)

    def test_nba_slate_ignores_player_props_as_forecasts(self):
        report = _report("todays nba games")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Thunder vs. Nuggets",
                question="Christian Braun: Assists O/U 0.5",
                url="https://polymarket.com/event/nba-okc-den-2026-04-10",
                outcome_prices=[("Yes", 0.0), ("No", 1.0)],
                engagement=_engagement(),
                market_type="player_prop",
                relevance=0.9,
                score=95,
            )
        ]

        self.assertEqual(forecast.synthesize_forecasts(report), [])

    def test_nba_watchlist_suppresses_player_props_for_generic_day_of_game_prompt(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Thunder vs. Nuggets",
                question="Christian Braun: Assists O/U 0.5",
                url="https://polymarket.com/event/nba-okc-den-2026-04-10",
                outcome_prices=[("Yes", 0.54), ("No", 0.46)],
                engagement=_engagement(),
                market_type="player_prop",
                market_signal_quality=0.82,
                volume_24h=500_000,
                best_bid=0.53,
                best_ask=0.55,
                spread=0.02,
                movement_24h=2.5,
                relevance=0.95,
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items, [])

    def test_near_certain_threshold_market_is_suppressed_without_strong_unresolved_signal(self):
        report = _report("crypto prediction markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above ___ on April 11?",
                question="Will the price of Bitcoin be above $64,000 on April 11?",
                url="https://polymarket.com/event/bitcoin-above-on-april-11",
                outcome_prices=[("Yes", 1.0), ("No", 0.0)],
                engagement=_engagement(volume=2_000_000, liquidity=800_000),
                market_type="threshold",
                market_signal_quality=0.86,
                volume_24h=2_000_000,
                best_bid=1.0,
                best_ask=1.0,
                spread=0.0,
                movement_24h=0.9,
                relevance=0.9,
                score=95,
            )
        ]

        self.assertEqual(market_watchlist.synthesize_market_watchlist(report), [])

    def test_crypto_threshold_forecast_rejects_conflicting_threshold_markets(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above ___ on April 19?",
                question="Will the price of Bitcoin be above $70,000 on April 19?",
                url="https://polymarket.com/event/bitcoin-above-on-april-19",
                outcome_prices=[("Yes", 1.0), ("No", 0.0)],
                engagement=_engagement(volume=2_000_000, liquidity=600_000),
                market_type="threshold",
                relevance=0.95,
                score=99,
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Bitcoin price range on Apr 19, 2026 at 5pm EDT?",
                question="Bitcoin price range on Apr 19, 2026?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC-26APR1917-B75875",
                ticker="KXBTC-26APR1917-B75875",
                event_ticker="KXBTC-26APR1917",
                series_ticker="KXBTC",
                current_probability=0.08,
                engagement=_engagement(volume=2_942, liquidity=0, open_interest=2_748),
                market_type="threshold",
                relevance=0.8,
                score=80,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertIsNone(forecasts[0].kalshi_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")
        self.assertLess(forecasts[0].forecast_probability, 0.20)
        self.assertIn("DEGRADED RUN WARNING", forecasts[0].degraded_warning)
        report.forecasts = forecasts
        self.assertIn("DEGRADED RUN WARNING", render.render_compact(report))

    def test_cs2_watchlist_prefers_direct_matches_and_suppresses_long_dated_title_market(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Wingman vs Nebula In Chaox (BO3) - Exort Series Main Stage",
                question="Counter-Strike: Wingman vs Nebula In Chaox (BO3) - Exort Series Main Stage",
                url="https://polymarket.com/event/cs2-wing-nic1-2026-04-21",
                outcome_prices=[("Wingman", 0.06), ("Nebula In Chaox", 0.94)],
                engagement=_engagement(volume=350_000, liquidity=150_000),
                market_signal_quality=0.82,
                volume_24h=350_000,
                best_bid=0.93,
                best_ask=0.95,
                spread=0.02,
                movement_24h=7.5,
                relevance=0.94,
                score=92,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Will Valve add Cache to the Map Pool by June 30, 2026?",
                question="Will Valve add Cache to the Map Pool by June 30, 2026?",
                url="https://polymarket.com/event/will-valve-will-add-cache-to-the-map-pool-by-end-of-january-519",
                outcome_prices=[("Yes", 0.36), ("No", 0.64)],
                engagement=_engagement(volume=120_000, liquidity=20_000),
                market_signal_quality=0.60,
                volume_24h=120_000,
                best_bid=0.60,
                best_ask=0.67,
                spread=0.07,
                movement_24h=7.0,
                relevance=0.60,
                score=70,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].market_type, "game_outcome")
        self.assertIn("Wingman vs Nebula", items[0].title)

    def test_cs2_watchlist_suppresses_map_props_for_generic_prompt(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Map 1: Odd/Even Total Kills?",
                question="Counter-Strike: AaB Esport vs Sangal ALTERS (BO3) - European Pro League Regular Group A",
                url="https://polymarket.com/event/cs2-aab-sng-2026-04-21",
                outcome_prices=[("Odd", 0.5), ("Even", 0.5)],
                engagement=_engagement(volume=90_000, liquidity=0),
                market_signal_quality=0.35,
                volume_24h=90_000,
                best_bid=0.0,
                best_ask=1.0,
                spread=1.0,
                movement_24h=0.0,
                relevance=0.90,
                score=65,
            )
        ]

        self.assertEqual(market_watchlist.synthesize_market_watchlist(report), [])

    def test_cs2_watchlist_rejects_generic_dev_log_catalyst(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Team One vs Team Two (BO3) - Qualifier",
                question="Counter-Strike: Team One vs Team Two (BO3) - Qualifier",
                url="https://polymarket.com/event/cs2-team1-team2-2026-04-21",
                outcome_prices=[("Team One", 0.44), ("Team Two", 0.56)],
                engagement=_engagement(volume=220_000, liquidity=80_000),
                market_signal_quality=0.74,
                volume_24h=220_000,
                best_bid=0.55,
                best_ask=0.57,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.90,
                score=86,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="CS2 Update DEV Log This is a Counter-Strike 2 client-side developer log from Dust II animation testing.",
                url="https://x.com/dev/status/1",
                author_handle="xTheWhale_",
                score=90,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("thin", items[0].catalyst_summary.lower())
        self.assertNotIn("DEV Log", items[0].catalyst_summary)

    def test_cs2_watchlist_rejects_watch_live_listing_catalyst(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Team One vs Team Two (BO3) - Qualifier",
                question="Counter-Strike: Team One vs Team Two (BO3) - Qualifier",
                url="https://polymarket.com/event/cs2-team1-team2-2026-04-21",
                outcome_prices=[("Team One", 0.44), ("Team Two", 0.56)],
                engagement=_engagement(volume=220_000, liquidity=80_000),
                market_signal_quality=0.74,
                volume_24h=220_000,
                best_bid=0.55,
                best_ask=0.57,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.90,
                score=86,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Watch live Team One vs Team Two today in Counter-Strike 2. Stream starts in 10 minutes.",
                url="https://x.com/dev/status/1",
                author_handle="watchpartyhub",
                score=90,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("thin", items[0].catalyst_summary.lower())
        self.assertNotIn("Watch live", items[0].catalyst_summary)

    def test_explicit_cs2_map_pool_prompt_allows_title_market(self):
        report = _report("CS2 map pool markets")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Will Valve add Cache to the Map Pool by June 30, 2026?",
                question="Will Valve add Cache to the Map Pool by June 30, 2026?",
                url="https://polymarket.com/event/will-valve-will-add-cache-to-the-map-pool-by-end-of-january-519",
                outcome_prices=[("Yes", 0.36), ("No", 0.64)],
                engagement=_engagement(volume=120_000, liquidity=20_000),
                market_signal_quality=0.60,
                volume_24h=120_000,
                best_bid=0.60,
                best_ask=0.67,
                spread=0.07,
                movement_24h=7.0,
                relevance=0.90,
                score=70,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].market_type, "esports_title")

    def test_cs2_watchlist_rejects_non_esports_strike_market(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="How many different countries will the US conduct military action against in 2026?",
                question="Will the US strike 6 countries in 2026?",
                url="https://polymarket.com/event/how-many-different-countries-will-the-us-strike-in-2026",
                outcome_prices=[("Yes", 0.11), ("No", 0.89)],
                engagement=_engagement(volume=361_000, liquidity=153_000),
                market_signal_quality=0.74,
                volume_24h=361_000,
                best_bid=0.89,
                best_ask=0.89,
                spread=0.0,
                movement_24h=4.5,
                relevance=0.65,
                score=88,
            )
        ]

        self.assertEqual(market_watchlist.synthesize_market_watchlist(report), [])

    def test_cs2_matchup_forecast_uses_direct_market_anchor(self):
        report = _report("Counter-Strike: Astralis vs G2 today")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                question="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                url="https://polymarket.com/event/cs2-astr-g2-2026-04-21",
                outcome_prices=[("Astralis", 0.47), ("G2", 0.53)],
                engagement=_engagement(volume=180_000, liquidity=90_000),
                market_signal_quality=0.77,
                volume_24h=180_000,
                best_bid=0.52,
                best_ask=0.54,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.95,
                score=88,
                market_type="game_outcome",
                end_date="2026-04-21",
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].favorite_label, "G2")
        self.assertNotIn("lineup", forecasts[0].why_line.lower())
        self.assertNotIn("tipoff", " ".join(forecasts[0].downside_catalysts).lower())

    def test_cs2_matches_today_returns_multi_row_slate_forecasts(self):
        report = _report("Counter-Strike 2 matches today")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                question="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                url="https://polymarket.com/event/cs2-astr-g2-2026-04-21",
                outcome_prices=[("Astralis", 0.47), ("G2", 0.53)],
                engagement=_engagement(volume=180_000, liquidity=90_000),
                market_signal_quality=0.77,
                volume_24h=180_000,
                best_bid=0.52,
                best_ask=0.54,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.95,
                score=88,
                market_type="game_outcome",
                end_date="2026-04-21",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Counter-Strike: fnatic vs Qual4 (BO3) - Conquest of Prague Online Stage Group Stage",
                question="Counter-Strike: fnatic vs Qual4 (BO3) - Conquest of Prague Online Stage Group Stage",
                url="https://polymarket.com/event/cs2-fnc-qual4-2026-04-21",
                outcome_prices=[("fnatic", 0.79), ("Qual4", 0.21)],
                engagement=_engagement(volume=120_000, liquidity=70_000),
                market_signal_quality=0.72,
                volume_24h=120_000,
                best_bid=0.78,
                best_ask=0.80,
                spread=0.02,
                movement_24h=4.0,
                relevance=0.91,
                score=82,
                market_type="game_outcome",
                end_date="2026-04-21",
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Will Valve add Cache to the Map Pool by June 30, 2026?",
                question="Will Valve add Cache to the Map Pool by June 30, 2026?",
                url="https://polymarket.com/event/will-valve-will-add-cache-to-the-map-pool-by-end-of-january-519",
                outcome_prices=[("Yes", 0.36), ("No", 0.64)],
                engagement=_engagement(volume=120_000, liquidity=20_000),
                market_signal_quality=0.60,
                volume_24h=120_000,
                best_bid=0.60,
                best_ask=0.67,
                spread=0.07,
                movement_24h=7.0,
                relevance=0.90,
                score=70,
                market_type="esports_title",
                end_date="2026-06-30",
            ),
            schema.PolymarketItem(
                id="PM4",
                title="Counter-Strike: Gentle Mates vs ASTRAL (BO3) - LORGAR RANKINGS Playoffs",
                question="Counter-Strike: Gentle Mates vs ASTRAL (BO3) - LORGAR RANKINGS Playoffs",
                url="https://polymarket.com/event/cs2-m8-ast-2026-04-25",
                outcome_prices=[("Gentle Mates", 0.90), ("ASTRAL", 0.10)],
                engagement=_engagement(volume=89, liquidity=9_000),
                market_signal_quality=0.30,
                volume_24h=89,
                best_bid=0.89,
                best_ask=0.91,
                spread=0.02,
                movement_24h=-1.0,
                relevance=0.80,
                score=28,
                market_type="game_outcome",
                end_datetime="2026-04-25T20:00:00Z",
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 2)
        self.assertTrue(all(item.anchor_source == "polymarket" for item in forecasts))
        self.assertTrue(all("Counter-Strike:" in item.title for item in forecasts))

    def test_cs2_matches_today_accepts_unknown_direct_match_market_types(self):
        report = _report("Counter-Strike 2 matches today")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                question="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                url="https://polymarket.com/event/cs2-astr-g2-2026-04-21",
                outcome_prices=[("Astralis", 0.47), ("G2", 0.53)],
                engagement=_engagement(volume=180_000, liquidity=90_000),
                market_signal_quality=0.77,
                volume_24h=180_000,
                best_bid=0.52,
                best_ask=0.54,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.95,
                score=88,
                market_type="unknown",
                end_date="2026-04-21",
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertIn("Astralis vs G2", forecasts[0].title)

    def test_cs2_matches_today_rejects_other_esports_titles_from_forecast_board(self):
        report = _report("Counter-Strike 2 matches today")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Valorant: Team One vs Team Two (BO3) - Group Stage",
                question="Valorant: Team One vs Team Two (BO3) - Group Stage",
                url="https://polymarket.com/event/val-team1-team2-2026-04-21",
                outcome_prices=[("Team One", 0.40), ("Team Two", 0.60)],
                engagement=_engagement(volume=180_000, liquidity=90_000),
                market_signal_quality=0.77,
                volume_24h=180_000,
                best_bid=0.59,
                best_ask=0.61,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.95,
                score=88,
                market_type="game_outcome",
                end_date="2026-04-21",
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")
        self.assertIn("DEGRADED RUN WARNING", forecasts[0].degraded_warning)

    def test_cs2_watchlist_today_excludes_later_date_rows_from_rendered_board(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                question="Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                url="https://polymarket.com/event/cs2-astr-g2-2026-04-21",
                outcome_prices=[("Astralis", 0.47), ("G2", 0.53)],
                engagement=_engagement(volume=180_000, liquidity=90_000),
                market_signal_quality=0.77,
                volume_24h=180_000,
                best_bid=0.52,
                best_ask=0.54,
                spread=0.02,
                movement_24h=3.0,
                relevance=0.95,
                score=88,
                market_type="game_outcome",
                end_date="2026-04-21",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Counter-Strike: Gentle Mates vs ASTRAL (BO3) - LORGAR RANKINGS Playoffs",
                question="Counter-Strike: Gentle Mates vs ASTRAL (BO3) - LORGAR RANKINGS Playoffs",
                url="https://polymarket.com/event/cs2-m8-ast-2026-04-25",
                outcome_prices=[("Gentle Mates", 0.90), ("ASTRAL", 0.10)],
                engagement=_engagement(volume=89, liquidity=9_000),
                market_signal_quality=0.30,
                volume_24h=89,
                best_bid=0.89,
                best_ask=0.91,
                spread=0.02,
                movement_24h=-1.0,
                relevance=0.80,
                score=28,
                market_type="game_outcome",
                end_datetime="2026-04-25T20:00:00Z",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("Astralis vs G2", items[0].title)

    def test_cs2_matches_today_handles_short_team_tags(self):
        report = _report("Counter-Strike 2 matches today")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                question="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                url="https://polymarket.com/event/cs2-z7-sashia-2026-04-21",
                outcome_prices=[("Z7 Esports", 0.02), ("Sashi Academy", 0.98)],
                engagement=_engagement(volume=42_000, liquidity=237_000),
                market_signal_quality=0.76,
                volume_24h=42_000,
                best_bid=0.99,
                best_ask=1.0,
                spread=0.01,
                movement_24h=0.0,
                relevance=0.90,
                score=75,
                market_type="game_outcome",
                end_date="2026-04-21",
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].favorite_label, "Sashi Academy")

    def test_cs2_map_pool_forecast_rejects_betting_style_why_line(self):
        report = _report("CS2 map pool markets")
        report.generated_at = "2026-04-21T18:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Will Valve add Cache to the Map Pool by June 30, 2026?",
                question="Will Valve add Cache to the Map Pool by June 30, 2026?",
                url="https://polymarket.com/event/will-valve-will-add-cache-to-the-map-pool-by-end-of-january-519",
                outcome_prices=[("Yes", 0.37), ("No", 0.63)],
                engagement=_engagement(volume=175_000, liquidity=5_000),
                market_signal_quality=0.62,
                volume_24h=175_000,
                best_bid=0.62,
                best_ask=0.64,
                spread=0.02,
                movement_24h=30.0,
                relevance=0.94,
                score=80,
                market_type="esports_title",
                end_date="2026-06-30",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="CS2 x VAL Streak Starter mASKED high usage plus strong map pool line feels too low for 3 maps",
                url="https://x.com/example/status/1",
                author_handle="betsfeed",
                score=70,
            ),
            schema.XItem(
                id="X2",
                text="How to improve the CS2 map pool before the Major. Cache and Cobblestone remain the obvious candidates for a future active-duty rotation.",
                url="https://x.com/example/status/2",
                author_handle="TheChefCS",
                score=75,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertNotIn("line feels too low", forecasts[0].why_line.lower())
        self.assertNotIn("streak starter", forecasts[0].why_line.lower())

    def test_render_compact_cs2_degraded_suppresses_generic_x_noise(self):
        report = _report("Counter-Strike 2 matches today")
        report.forecasts = [
            schema.ForecastItem(
                title="Counter-Strike 2 matches today",
                forecast_probability=0.53,
                forecast_range_low=0.48,
                forecast_range_high=0.58,
                favorite_label="Yes",
                anchor_source="model_implied",
                market_view="No clean Polymarket or Kalshi market found.",
                why_line="No clean market exists and no high-signal roster, patch, veto, or tournament-context driver surfaced in the last 24 hours.",
                confidence_level="low",
                uncertainty="No clean market exists, so this is model-implied and should be treated cautiously.",
                degraded_warning="DEGRADED RUN WARNING: no date-compatible direct eSports market cleared anchoring, so this is a lower-confidence model-implied forecast.",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Counter-Strike 2 has pushed Animgraph 2 live. The new animation system changes player and weapon animations in matches.",
                url="https://x.com/example/status/1",
                author_handle="World1gg",
                score=60,
            ),
            schema.XItem(
                id="X2",
                text="@nikitabier can you do one for Counter-Strike 2?",
                url="https://x.com/example/status/2",
                author_handle="rattecs",
                score=44,
            ),
        ]

        compact = render.render_compact(report)

        self.assertIn("No high-signal X posts found for this esports forecast.", compact)
        self.assertNotIn("Animgraph 2", compact)
        self.assertNotIn("@nikitabier", compact)

    def test_render_compact_esports_prop_degraded_suppresses_generic_player_name_noise(self):
        report = _report("Faker solo kills tonight")
        report.forecasts = [
            schema.ForecastItem(
                title="Faker solo kills tonight",
                forecast_probability=0.53,
                forecast_range_low=0.48,
                forecast_range_high=0.58,
                favorite_label="Yes",
                anchor_source="model_implied",
                market_view="No clean Polymarket or Kalshi market found.",
                why_line="No clean market exists and no high-signal player-specific driver surfaced in the last 24 hours.",
                confidence_level="low",
                uncertainty="No clean market exists, so this is model-implied and should be treated cautiously.",
                degraded_warning="DEGRADED RUN WARNING: no clean Polymarket/Kalshi market cleared anchoring, so this is a lower-confidence model-implied forecast.",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="solo faker de la xenofobia y el rey demonio de japon entero",
                url="https://x.com/example/status/1",
                author_handle="randomfan",
                score=52,
            ),
            schema.XItem(
                id="X2",
                text="buenos dias solo a faker",
                url="https://x.com/example/status/2",
                author_handle="anotherfan",
                score=40,
            ),
        ]

        compact = render.render_compact(report)

        self.assertIn("No high-signal X posts found for this esports forecast.", compact)
        self.assertNotIn("buenos dias solo a faker", compact.lower())

    def test_broad_esports_watchlist_prefers_mixed_titles_over_only_stale_lol(self):
        report = _report("esports markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="LoL: Cloud9 vs Sentinels (BO3) - Qualifier",
                question="LoL: Cloud9 vs Sentinels (BO3) - Qualifier",
                url="https://polymarket.com/event/lol-c9-sen-2026-04-21",
                outcome_prices=[("Cloud9", 0.0), ("Sentinels", 1.0)],
                engagement=_engagement(volume=900_000, liquidity=400_000),
                market_signal_quality=0.99,
                volume_24h=900_000,
                best_bid=1.0,
                best_ask=1.0,
                spread=0.0,
                movement_24h=-60.0,
                relevance=0.98,
                score=96,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="LoL: LYON vs FlyQuest (BO3) - Qualifier",
                question="LoL: LYON vs FlyQuest (BO3) - Qualifier",
                url="https://polymarket.com/event/lol-ly-fly-2026-04-21",
                outcome_prices=[("LYON", 0.0), ("FlyQuest", 1.0)],
                engagement=_engagement(volume=650_000, liquidity=365_000),
                market_signal_quality=0.98,
                volume_24h=650_000,
                best_bid=1.0,
                best_ask=1.0,
                spread=0.0,
                movement_24h=-70.0,
                relevance=0.97,
                score=95,
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Valorant: AKA HERO vs Dortmund eSports (BO3) - Group Stage",
                question="Valorant: AKA HERO vs Dortmund eSports (BO3) - Group Stage",
                url="https://polymarket.com/event/val-ah-dor-2026-04-21",
                outcome_prices=[("AKA HERO", 0.12), ("Dortmund eSports", 0.88)],
                engagement=_engagement(volume=47_000, liquidity=484_000),
                market_signal_quality=0.92,
                volume_24h=47_000,
                best_bid=0.87,
                best_ask=0.89,
                spread=0.02,
                movement_24h=-40.9,
                relevance=0.93,
                score=80,
            ),
            schema.PolymarketItem(
                id="PM4",
                title="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                question="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                url="https://polymarket.com/event/cs2-z7-sashia-2026-04-21",
                outcome_prices=[("Z7 Esports", 0.02), ("Sashi Academy", 0.98)],
                engagement=_engagement(volume=42_000, liquidity=237_000),
                market_signal_quality=0.76,
                volume_24h=42_000,
                best_bid=0.99,
                best_ask=1.0,
                spread=0.01,
                movement_24h=0.0,
                relevance=0.91,
                score=75,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)
        titles = " || ".join(item.title for item in items)

        self.assertTrue(any("Valorant:" in item.title for item in items))
        self.assertTrue(any("Counter-Strike:" in item.title for item in items))
        self.assertLessEqual(sum(1 for item in items if item.title.startswith("LoL:")), 1, titles)
        self.assertFalse(any("2026-04-24" in (item.url or "") for item in items), titles)

    def test_broad_esports_watchlist_drops_rows_more_than_one_day_past_today_window(self):
        report = _report("esports markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="LoL: Hanwha Life Esports Challengers vs Dplus KIA Challengers (BO3) - LCK Challengers League Rounds 1-2",
                question="LoL: Hanwha Life Esports Challengers vs Dplus KIA Challengers (BO3) - LCK Challengers League Rounds 1-2",
                url="https://polymarket.com/event/lol-hle-dkc-2026-04-22",
                outcome_prices=[("Hanwha Life Esports Challengers", 0.34), ("Dplus KIA Challengers", 0.66)],
                engagement=_engagement(volume=121_000, liquidity=146_000),
                market_signal_quality=0.86,
                volume_24h=121_000,
                best_bid=0.34,
                best_ask=0.35,
                spread=0.01,
                movement_24h=-12.5,
                relevance=0.91,
                score=82,
                end_date="2026-04-22",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Valorant: 9z Team vs Melser Kindergarten (BO3) - VCL Latin America South: ACE Masters Group A",
                question="Valorant: 9z Team vs Melser Kindergarten (BO3) - VCL Latin America South: ACE Masters Group A",
                url="https://polymarket.com/event/val-9z-mk-2026-04-24",
                outcome_prices=[("9z Team", 0.34), ("Melser Kindergarten", 0.66)],
                engagement=_engagement(volume=6_000, liquidity=3_000),
                market_signal_quality=0.56,
                volume_24h=6_000,
                best_bid=0.31,
                best_ask=0.36,
                spread=0.05,
                movement_24h=0.0,
                relevance=0.88,
                score=54,
                end_date="2026-04-24",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("LoL:", items[0].title)
        self.assertNotIn("2026-04-24", items[0].url or "")

    def test_broad_esports_watchlist_rejects_unrelated_org_catalyst(self):
        report = _report("esports markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                question="Counter-Strike: Z7 Esports vs Sashi Academy (BO3) - European Pro League Regular Group C",
                url="https://polymarket.com/event/cs2-z7-sashia-2026-04-21",
                outcome_prices=[("Z7 Esports", 0.02), ("Sashi Academy", 0.98)],
                engagement=_engagement(volume=42_000, liquidity=237_000),
                market_signal_quality=0.76,
                volume_24h=42_000,
                best_bid=0.99,
                best_ask=1.0,
                spread=0.01,
                movement_24h=0.0,
                relevance=0.91,
                score=75,
            ),
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="THE NEXT CHAPTER STARTS WITH YOU! Join Lakers Esports in downtown Chicago at RooseveltU. Scholarship applications are open now.",
                url="https://x.com/example/status/1",
                author_handle="RULakersgg",
                score=88,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("thin", items[0].catalyst_summary.lower())
        self.assertNotIn("Lakers Esports", items[0].catalyst_summary)

    def test_cs2_player_prop_watchlist_rejects_non_esports_market(self):
        report = _report("CS2 player-prop markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="How many different countries will the US conduct military action against in 2026?",
                question="How many different countries will the US conduct military action against in 2026?",
                url="https://polymarket.com/event/how-many-different-countries-will-the-us-strike-in-2026",
                outcome_prices=[("No", 0.89), ("Yes", 0.11)],
                engagement=_engagement(volume=28_000, liquidity=159_000),
                market_signal_quality=0.74,
                volume_24h=28_000,
                best_bid=0.88,
                best_ask=0.89,
                spread=0.01,
                movement_24h=0.2,
                relevance=0.31,
                score=61,
                market_type="unknown",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Counter-Strike 2: donk total kills > 18.5 - Map 1",
                question="Will donk get more than 18.5 kills?",
                url="https://polymarket.com/event/cs2-donk-kills-2026-04-21",
                outcome_prices=[("Yes", 0.56), ("No", 0.44)],
                engagement=_engagement(volume=12_000, liquidity=8_000),
                market_signal_quality=0.52,
                volume_24h=12_000,
                best_bid=0.55,
                best_ask=0.57,
                spread=0.02,
                movement_24h=2.0,
                relevance=0.82,
                score=54,
                market_type="esports_prop",
                end_date="2026-04-21",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertIn("donk", items[0].title.lower())
        self.assertEqual(items[0].market_type, "esports_prop")

    def test_cs2_watchlist_still_rejects_prop_only_board_for_generic_prompt(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Counter-Strike 2: donk total kills > 18.5 - Map 1",
                question="Will donk get more than 18.5 kills?",
                url="https://polymarket.com/event/cs2-donk-kills-2026-04-22",
                outcome_prices=[("Yes", 0.56), ("No", 0.44)],
                engagement=_engagement(volume=12_000, liquidity=8_000),
                market_signal_quality=0.52,
                volume_24h=12_000,
                best_bid=0.55,
                best_ask=0.57,
                spread=0.02,
                movement_24h=2.0,
                relevance=0.82,
                score=54,
                market_type="esports_prop",
                end_date="2026-04-22",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items, [])

    def test_esports_prop_empty_state_is_precise(self):
        report = _report("CS2 player-prop markets to watch today")

        compact = render.render_compact(report)

        self.assertIn("No high-quality watchlist markets found.", compact)
        self.assertIn("no compatible same-day player-prop markets survived", compact.lower())

    def test_kalshi_matchup_signature_matches_polymarket_nba_game(self):
        poly_item = schema.PolymarketItem(
            id="PM1",
            title="Suns vs. Thunder",
            question="Suns vs. Thunder",
            url="https://polymarket.com/event/nba-phx-okc-2026-04-22",
            outcome_prices=[("Suns", 0.07), ("Thunder", 0.93)],
            engagement=_engagement(),
            market_type="game_outcome",
        )
        kalshi_item = schema.KalshiItem(
            id="KA1",
            title="Game 2: Phoenix at Oklahoma City",
            question="Game 2: Phoenix at Oklahoma City Winner?",
            url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22PHXOKC-OKC",
            ticker="KXNBAGAME-26APR22PHXOKC-OKC",
            event_ticker="KXNBAGAME-26APR22PHXOKC",
            current_probability=0.93,
            market_type="game_outcome",
        )

        matched = forecast._matching_kalshi_for_polymarket(poly_item, [kalshi_item], "2026-04-22")

        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, "KA1")

    def test_kalshi_only_nba_slate_returns_per_game_forecasts(self):
        report = schema.Report(
            topic="tomorrows nba games",
            range_from="2026-04-21",
            range_to="2026-04-21",
            generated_at="2026-04-21T00:00:00+00:00",
            mode="kalshi",
        )
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Game 2: Phoenix at Oklahoma City",
                question="Game 2: Phoenix at Oklahoma City Winner?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22PHXOKC-OKC",
                ticker="KXNBAGAME-26APR22PHXOKC-OKC",
                event_ticker="KXNBAGAME-26APR22PHXOKC",
                current_probability=0.93,
                implied_probability=0.93,
                best_bid=0.92,
                best_ask=0.93,
                spread=0.01,
                movement_24h=-1.0,
                volume_24h=66_610.46,
                market_signal_quality=0.63,
                market_type="game_outcome",
                date="2026-04-18",
                date_confidence="high",
                engagement=_engagement(volume=66_610.46, liquidity=0, open_interest=202_240.62),
                end_date="2026-05-07",
                relevance=0.74,
                score=75,
            ),
            schema.KalshiItem(
                id="KA2",
                title="Game 2: Orlando at Detroit",
                question="Game 2: Orlando at Detroit Winner?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22ORLDET-DET",
                ticker="KXNBAGAME-26APR22ORLDET-DET",
                event_ticker="KXNBAGAME-26APR22ORLDET",
                current_probability=0.86,
                implied_probability=0.86,
                best_bid=0.85,
                best_ask=0.86,
                spread=0.01,
                movement_24h=1.0,
                volume_24h=54_210.0,
                market_signal_quality=0.61,
                market_type="game_outcome",
                date="2026-04-18",
                date_confidence="high",
                engagement=_engagement(volume=54_210.0, liquidity=0, open_interest=95_000.0),
                end_date="2026-05-07",
                relevance=0.72,
                score=68,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 2)
        self.assertTrue(all(item.anchor_source == "kalshi" for item in forecasts))
        self.assertEqual(forecasts[0].title, "Game 2: Phoenix at Oklahoma City")
        self.assertEqual(forecasts[1].title, "Game 2: Orlando at Detroit")

    def test_crypto_threshold_forecast_keeps_matching_threshold_market(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above $100,000 this week?",
                question="Will the price of Bitcoin be above $100,000 this week?",
                url="https://polymarket.com/event/bitcoin-above-100k-this-week",
                outcome_prices=[("Yes", 0.22), ("No", 0.78)],
                engagement=_engagement(volume=800_000, liquidity=250_000),
                market_type="threshold",
                relevance=0.95,
                score=95,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].favorite_label, "Yes")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.22)

    def test_crypto_threshold_forecast_does_not_blend_incompatible_kalshi_market(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above $100,000 this week?",
                question="Will the price of Bitcoin be above $100,000 this week?",
                url="https://polymarket.com/event/bitcoin-above-100k-this-week",
                outcome_prices=[("Yes", 0.22), ("No", 0.78)],
                engagement=_engagement(volume=800_000, liquidity=250_000),
                market_type="threshold",
                relevance=0.95,
                score=95,
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Bitcoin price range on Apr 19, 2026 at 5pm EDT?",
                question="Bitcoin price range on Apr 19, 2026?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC-26APR1917-B75875",
                ticker="KXBTC-26APR1917-B75875",
                event_ticker="KXBTC-26APR1917",
                series_ticker="KXBTC",
                current_probability=0.08,
                engagement=_engagement(volume=2_942, liquidity=0, open_interest=2_748),
                market_type="threshold",
                relevance=0.8,
                score=80,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertIsNone(forecasts[0].kalshi_market_id)
        self.assertNotIn("Kalshi", forecasts[0].market_view)

    def test_crypto_forecast_catalysts_do_not_use_sports_wording(self):
        report = _report("Bitcoin above 100k this week")

        forecasts = forecast.synthesize_forecasts(report)
        catalyst_text = " ".join(forecasts[0].upside_catalysts + forecasts[0].downside_catalysts).lower()

        self.assertIn("spot price", catalyst_text)
        for term in ("lineup", "injury", "rest", "tipoff"):
            self.assertNotIn(term, catalyst_text)

    def test_broad_closing_soon_rejects_unrelated_stock_promo_catalyst(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin Up or Down - April 20, 4AM ET",
                question="Bitcoin Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/bitcoin-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.30), ("Down", 0.70)],
                engagement=_engagement(volume=24_000, liquidity=6_000),
                market_type="crypto_daily",
                market_signal_quality=0.79,
                volume_24h=24_000,
                best_bid=0.29,
                best_ask=0.30,
                spread=0.01,
                movement_24h=-21.0,
                relevance=0.95,
                minutes_to_close=17,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Big thanks to @PriyRaval - stocks are on a tear! He drops daily winners that rise super fast. You need this in your feed. #StockMarket #Inflation",
                url="https://x.com/example/status/1",
                author_handle="promo",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertEqual(items[0].evidence_refs, [])
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_crypto_market_specific_catalyst_is_accepted(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Ethereum Up or Down - April 20, 4AM ET",
                question="Ethereum Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/ethereum-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.22), ("Down", 0.78)],
                engagement=_engagement(volume=50_000, liquidity=25_000),
                market_type="crypto_daily",
                market_signal_quality=0.80,
                volume_24h=50_000,
                best_bid=0.22,
                best_ask=0.23,
                spread=0.01,
                movement_24h=-18.0,
                relevance=0.95,
                minutes_to_close=15,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Ethereum volatility jumps as ETF flow data and liquidation pressure hit ETH price support before the daily close.",
                url="https://x.com/example/status/2",
                author_handle="crypto",
                score=92,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("Ethereum volatility", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)
        self.assertEqual(items[0].evidence_refs, ["X1 https://x.com/example/status/2"])

    def test_soccer_watchlist_rejects_unrelated_promo_and_requires_match_overlap(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="FK Oleksandriya vs. RNK Veres Rivne",
                question="Will FK Oleksandriya win on 2026-04-20?",
                url="https://polymarket.com/event/ukr1-ole-ver-2026-04-20",
                outcome_prices=[("FK Oleksandriya", 0.32), ("RNK Veres Rivne", 0.38)],
                engagement=_engagement(volume=10_000, liquidity=10_000),
                market_type="game_outcome",
                market_signal_quality=0.45,
                volume_24h=10_000,
                relevance=0.9,
                minutes_to_close=77,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Daily winners are on fire and my VIP picks keep cashing.",
                url="https://x.com/example/status/3",
                author_handle="promo",
                score=99,
            ),
            schema.XItem(
                id="X2",
                text="FK Oleksandriya vs RNK Veres Rivne is delayed by heavy rain with the live score still 0-0.",
                url="https://x.com/example/status/4",
                author_handle="matchreport",
                score=80,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("FK Oleksandriya", items[0].catalyst_summary)
        self.assertNotIn("Daily winners", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)

    def test_nba_watchlist_rejects_ticket_available_as_catalyst(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Lakers vs. Rockets",
                question="Lakers vs. Rockets",
                url="https://polymarket.com/event/nba-lal-hou-2026-04-20",
                outcome_prices=[("Rockets", 0.58), ("Lakers", 0.42)],
                engagement=_engagement(volume=100_000, liquidity=100_000),
                market_type="game_outcome",
                market_signal_quality=0.80,
                volume_24h=100_000,
                spread=0.01,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="I have Lakers Rockets tickets available section 117 row 6, DM if interested.",
                url="https://x.com/tickets/status/1",
                author_handle="tickets",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_nba_watchlist_rejects_promotional_picks_chatter_as_catalyst(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Cavaliers", 0.79), ("Raptors", 0.21)],
                engagement=_engagement(volume=100_000, liquidity=100_000),
                market_type="game_outcome",
                market_signal_quality=0.80,
                volume_24h=100_000,
                spread=0.01,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Tomorrow NBA most popular bets: Cavaliers Raptors. Stop missing out, VIP picks keep cashing.",
                url="https://x.com/promo/status/1",
                author_handle="promo",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_nba_watchlist_accepts_clean_exact_date_line_movement_catalyst(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Cavaliers", 0.79), ("Raptors", 0.21)],
                engagement=_engagement(volume=100_000, liquidity=100_000),
                market_type="game_outcome",
                market_signal_quality=0.80,
                volume_24h=100_000,
                spread=0.01,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Raptors vs Cavaliers April 20 moneyline moved toward Cleveland after the injury report listed Toronto starters questionable.",
                url="https://x.com/reporter/status/1",
                author_handle="reporter",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("moneyline moved", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)

    def test_nba_watchlist_accepts_clean_availability_catalyst(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Cavaliers", 0.79), ("Raptors", 0.21)],
                engagement=_engagement(volume=100_000, liquidity=100_000),
                market_type="game_outcome",
                market_signal_quality=0.80,
                volume_24h=100_000,
                spread=0.01,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Raptors vs Cavaliers April 20 injury report: Cleveland starter is available and Toronto starter remains questionable.",
                url="https://x.com/reporter/status/2",
                author_handle="reporter",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("starter is available", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)

    def test_weather_market_requires_location_specific_forecast_evidence(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Highest temperature in Shanghai on April 20?",
                question="Will the highest temperature in Shanghai be 18C on April 20?",
                url="https://polymarket.com/event/highest-temperature-in-shanghai-on-april-20-2026",
                outcome_prices=[("Yes", 0.86), ("No", 0.14)],
                engagement=_engagement(volume=100_000, liquidity=50_000),
                market_type="weather_binary",
                market_signal_quality=0.70,
                volume_24h=100_000,
                best_bid=0.86,
                best_ask=0.87,
                spread=0.01,
                relevance=0.95,
                minutes_to_close=120,
                closing_soon_reason="closing_soon",
            )
        ]
        report.web = [
            schema.WebSearchItem(
                id="W1",
                title="Beijing weather update",
                url="https://example.com/beijing",
                source_domain="example.com",
                snippet="The forecast model shows warmer temperatures and rain chances in Beijing.",
                score=90,
            ),
            schema.WebSearchItem(
                id="W2",
                title="Shanghai weather forecast",
                url="https://example.com/shanghai",
                source_domain="example.com",
                snippet="Shanghai forecast models show the highest temperature near 18C today.",
                score=80,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("Shanghai weather forecast", items[0].catalyst_summary)
        self.assertNotIn("Beijing", items[0].catalyst_summary)

    def test_tech_watchlist_requires_company_specific_entity_match(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Best Chinese AI Company end of April?",
                question="Will DeepSeek have the best AI model at the end of April 2026?",
                url="https://polymarket.com/event/best-chinese-ai-company-end-of-april",
                outcome_prices=[("Alibaba", 0.69), ("DeepSeek", 0.23)],
                engagement=_engagement(volume=24_000, liquidity=41_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=24_000,
                relevance=0.95,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Claude Opus 4.7 launched April 16, 2026 and remains Anthropic's top coding model.",
                url="https://x.com/grok/status/1",
                author_handle="grok",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")

    def test_tech_watchlist_keeps_matching_company_specific_catalyst(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/which-company-has-the-best-coding-ai-model-end-of-april",
                outcome_prices=[("Anthropic", 0.94), ("OpenAI", 0.06)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                relevance=0.95,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Claude Opus 4.7 launched April 16, 2026 and remains Anthropic's top model for coding benchmarks.",
                url="https://x.com/grok/status/2",
                author_handle="grok",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("Anthropic", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)

    def test_tech_watchlist_rejects_generic_tool_directory_chatter(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/which-company-has-the-best-coding-ai-model-end-of-april",
                outcome_prices=[("Anthropic", 0.94), ("OpenAI", 0.06)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                relevance=0.95,
            )
        ]
        report.reddit = [
            schema.RedditItem(
                id="R1",
                title="I built an MCP bridge that connects AI coding tools to a local Ollama instance and would love feedback.",
                url="https://www.reddit.com/r/ollama/comments/example",
                subreddit="ollama",
                score=60,
                relevance=0.7,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_tech_watchlist_rejects_mixed_competitor_catalyst(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/which-company-has-the-best-coding-ai-model-end-of-april",
                outcome_prices=[("Anthropic", 0.94), ("OpenAI", 0.06)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                relevance=0.95,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="China's Anthropic--Zhipu comparison still points to Zhipu's model momentum in coding benchmarks.",
                url="https://x.com/example/status/3",
                author_handle="example",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")

    def test_long_dated_zero_volume_tech_market_is_suppressed_when_stronger_rows_exist(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/coding-ai-april",
                outcome_prices=[("Anthropic", 0.94), ("OpenAI", 0.06)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                end_date="2026-04-30",
                relevance=0.95,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Will any AI model reach 1550 Coding Arena Score by June 30, 2026?",
                question="Will any AI model reach 1550 Coding Arena Score by June 30, 2026?",
                url="https://polymarket.com/event/coding-ai-june",
                outcome_prices=[("Yes", 0.86), ("No", 0.14)],
                engagement=_engagement(volume=3_000, liquidity=6_000),
                market_type="threshold",
                market_signal_quality=0.44,
                volume_24h=3_000,
                end_date="2026-06-30",
                relevance=0.95,
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Best Chinese AI Company end of April?",
                question="Will DeepSeek have the best AI model at the end of April 2026?",
                url="https://polymarket.com/event/china-ai-april",
                outcome_prices=[("Alibaba", 0.69), ("DeepSeek", 0.23)],
                engagement=_engagement(volume=24_000, liquidity=41_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=24_000,
                end_date="2026-04-30",
                relevance=0.95,
            ),
            schema.PolymarketItem(
                id="PM4",
                title="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                question="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                url="https://polymarket.com/event/coding-ai-december",
                outcome_prices=[("Yes", 0.93), ("No", 0.07)],
                engagement=_engagement(volume=0, liquidity=8_000),
                market_type="threshold",
                market_signal_quality=0.40,
                volume_24h=0,
                end_date="2026-12-31",
                relevance=0.95,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertNotIn("December 31, 2026", " ".join(item.question for item in items))

    def test_near_term_company_market_outranks_long_dated_threshold_row(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/coding-ai-april",
                outcome_prices=[("Anthropic", 0.72), ("OpenAI", 0.28)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                end_date="2026-04-30",
                relevance=0.95,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                question="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                url="https://polymarket.com/event/coding-ai-december",
                outcome_prices=[("Yes", 0.63), ("No", 0.37)],
                engagement=_engagement(volume=0, liquidity=8_000),
                market_type="threshold",
                market_signal_quality=0.40,
                volume_24h=0,
                end_date="2026-12-31",
                relevance=0.95,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].source_item_id, "PM1")

    def test_long_dated_tech_threshold_drops_when_two_near_term_company_rows_exist(self):
        report = _report("AI coding tools markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Which company has the best Coding AI model end of April?",
                question="Will Anthropic have the best Coding AI model at the end of April 2026?",
                url="https://polymarket.com/event/coding-ai-april",
                outcome_prices=[("Anthropic", 0.72), ("OpenAI", 0.28)],
                engagement=_engagement(volume=93_000, liquidity=115_000),
                market_type="unknown",
                market_signal_quality=0.55,
                volume_24h=93_000,
                end_date="2026-04-30",
                relevance=0.95,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Best Chinese AI Company end of April?",
                question="Will DeepSeek have the best AI model at the end of April 2026?",
                url="https://polymarket.com/event/best-chinese-ai-company-end-of-april",
                outcome_prices=[("Alibaba", 0.68), ("DeepSeek", 0.22)],
                engagement=_engagement(volume=60_000, liquidity=40_000),
                market_type="unknown",
                market_signal_quality=0.54,
                volume_24h=60_000,
                end_date="2026-04-30",
                relevance=0.93,
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                question="Will any AI model reach 1560 Coding Arena Score by December 31, 2026?",
                url="https://polymarket.com/event/coding-ai-december",
                outcome_prices=[("Yes", 0.63), ("No", 0.37)],
                engagement=_engagement(volume=0, liquidity=8_000),
                market_type="threshold",
                market_signal_quality=0.40,
                volume_24h=0,
                end_date="2026-12-31",
                relevance=0.95,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual([item.source_item_id for item in items], ["PM1", "PM2"])
        self.assertEqual(report.evidence_fusion_stats["debug_counters"]["suppressed_long_dated_watchlist_candidates"], 1)

    def test_fused_watchlist_driver_uses_same_market_specific_filter(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin Up or Down - April 20, 4AM ET",
                question="Bitcoin Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/bitcoin-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.30), ("Down", 0.70)],
                engagement=_engagement(volume=24_000, liquidity=6_000),
                market_type="crypto_daily",
                market_signal_quality=0.79,
                volume_24h=24_000,
                spread=0.01,
                relevance=0.95,
                minutes_to_close=17,
                closing_soon_reason="closing_soon",
            )
        ]
        fused = evidence_fusion.FusionResult(
            drivers=[
                evidence_fusion.FusedEvidence(
                    text="Inflation is moving markets, and these daily stock winners are on a tear.",
                    source="x",
                    source_item_id="X1",
                    author_key="x:promo",
                    cluster_key="inflation markets",
                    score=0.95,
                )
            ],
            candidate_count=1,
            cluster_count=1,
        )

        with mock.patch("scripts.lib.market_watchlist.evidence_fusion.fuse_evidence", return_value=fused):
            items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_render_uses_neutral_game_status_for_scheduled_watch_rows(self):
        report = _report("NBA markets to watch today")
        report.market_watchlist = [
            schema.MarketWatchItem(
                id="MW1",
                title="Lakers vs. Rockets",
                question="Lakers vs. Rockets",
                venue="Polymarket",
                url="https://polymarket.com/event/lakers-rockets",
                outcome_label="Lakers",
                probability=0.58,
                market_type="game_outcome",
                rank_score=62,
                why_ranks="strong market signal",
                market_signal="Polymarket; 58% implied",
                catalyst_summary="Catalyst context is thin; ranking is mostly market-signal driven.",
                risk="Fresh news or market repricing could change the ranking.",
                live_game_context="NBA Scheduled; start 2026-04-21T23:30:00Z",
            )
        ]

        output = render.render_compact(report)

        self.assertIn("Game status: NBA Scheduled", output)
        self.assertNotIn("Live game: NBA Scheduled", output)

    def test_nba_watchlist_keeps_mixed_board_but_prefers_direct_game_over_same_matchup_series(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-21",
                outcome_prices=[("Trail Blazers", 0.16), ("Spurs", 0.84)],
                engagement=_engagement(volume=1_600_000, liquidity=4_700_000),
                market_type="game_outcome",
                market_signal_quality=0.86,
                volume_24h=1_600_000,
                spread=0.01,
                relevance=0.95,
                end_date="2026-04-22",
                live_game_context="NBA Tue, April 21st at 8:00 PM EDT; start 2026-04-22T00:00Z",
                live_match_confidence=0.72,
                live_match_reason="direct_match",
                resolvability="sports game outcome; verify live score and market rules",
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Spread: Spurs (-11.5)",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-spread",
                outcome_prices=[("Spurs", 0.52), ("Blazers", 0.48)],
                engagement=_engagement(volume=900_000, liquidity=1_400_000),
                market_type="team_prop",
                market_signal_quality=0.84,
                volume_24h=900_000,
                spread=0.01,
                relevance=0.95,
                end_date="2026-04-22",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                question="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-spurs-vs-trail-blazers",
                outcome_prices=[("Spurs", 0.96), ("Blazers", 0.04)],
                engagement=_engagement(volume=23_000, liquidity=29_000),
                market_type="futures",
                market_signal_quality=0.64,
                volume_24h=23_000,
                spread=0.02,
                relevance=0.95,
                end_date="2026-05-04",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].source_item_id, "PM1")
        self.assertEqual(items[0].watchlist_scope, "game")
        self.assertEqual(items[1].source_item_id, "PM2")
        self.assertEqual(items[1].watchlist_scope, "series")

    def test_nba_watchlist_series_label_renders_explicitly(self):
        report = _report("NBA markets to watch today")
        report.market_watchlist = [
            schema.MarketWatchItem(
                id="MW1",
                title="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                question="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                venue="Polymarket",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-spurs-vs-trail-blazers",
                outcome_label="Spurs",
                probability=0.96,
                market_type="futures",
                watchlist_scope="series",
                rank_score=53,
                why_ranks="playoff series, strong market signal",
                market_signal="Polymarket; 96% implied",
                catalyst_summary="Catalyst context is thin; ranking is mostly market-signal driven.",
                risk="Fresh news or market repricing could change the ranking.",
            )
        ]

        output = render.render_compact(report)

        self.assertIn("Outcome: Polymarket Playoff series - Spurs 96%", output)

    def test_explicit_nba_series_prompt_can_be_series_heavy(self):
        report = _report("NBA playoff series markets to watch")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="NBA Playoffs: Who Will Win Series? - Lakers vs. Rockets ",
                question="NBA Playoffs: Who Will Win Series? - Lakers vs. Rockets ",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-lakers-vs-rockets",
                outcome_prices=[("Rockets", 0.68), ("Lakers", 0.32)],
                engagement=_engagement(volume=51_000, liquidity=23_000),
                market_type="futures",
                market_signal_quality=0.67,
                volume_24h=51_000,
                spread=0.03,
                relevance=0.95,
                end_date="2026-05-04",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-21",
                outcome_prices=[("Trail Blazers", 0.16), ("Spurs", 0.84)],
                engagement=_engagement(volume=1_600_000, liquidity=4_700_000),
                market_type="game_outcome",
                market_signal_quality=0.86,
                volume_24h=1_600_000,
                spread=0.01,
                relevance=0.92,
                end_date="2026-04-22",
                live_game_context="NBA Tue, April 21st at 8:00 PM EDT; start 2026-04-22T00:00Z",
                live_match_confidence=0.72,
                live_match_reason="direct_match",
                resolvability="sports game outcome; verify live score and market rules",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].watchlist_scope, "series")

    def test_kalshi_nba_game_row_survives_mixed_watchlist_scope_filter(self):
        report = _report("NBA markets to watch today")
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Game 3: New York at Atlanta",
                question="Game 3: New York at Atlanta Winner?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR23NYKATL-NYK",
                ticker="KXNBAGAME-26APR23NYKATL-NYK",
                event_ticker="KXNBAGAME-26APR23NYKATL",
                current_probability=0.51,
                implied_probability=0.51,
                best_bid=0.50,
                best_ask=0.51,
                spread=0.01,
                movement_24h=-5.0,
                volume_24h=93_224.44,
                market_signal_quality=0.64,
                market_type="game_outcome",
                date="2026-04-16",
                date_confidence="high",
                engagement=_engagement(volume=93_224.44, liquidity=0, open_interest=91_807.51),
                end_date="2026-05-07",
                relevance=0.75,
                why_relevant="Kalshi market: Game 3: New York at Atlanta Winner?",
                score=76,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].venue, "Kalshi")
        self.assertEqual(items[0].watchlist_scope, "game")
        self.assertEqual(items[0].market_type, "game_outcome")

    def test_weak_nba_series_row_is_suppressed_when_multiple_clean_game_rows_exist(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-21",
                outcome_prices=[("Trail Blazers", 0.16), ("Spurs", 0.84)],
                engagement=_engagement(volume=1_600_000, liquidity=4_700_000),
                market_type="game_outcome",
                market_signal_quality=0.86,
                volume_24h=1_600_000,
                spread=0.01,
                relevance=0.95,
                end_date="2026-04-22",
                live_game_context="NBA Tue, April 21st at 8:00 PM EDT; start 2026-04-22T00:00Z",
                live_match_confidence=0.72,
                live_match_reason="direct_match",
                resolvability="sports game outcome; verify live score and market rules",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="76ers vs. Celtics",
                question="76ers vs. Celtics",
                url="https://polymarket.com/event/nba-phi-bos-2026-04-21",
                outcome_prices=[("76ers", 0.12), ("Celtics", 0.88)],
                engagement=_engagement(volume=1_800_000, liquidity=4_300_000),
                market_type="game_outcome",
                market_signal_quality=0.85,
                volume_24h=1_800_000,
                spread=0.01,
                relevance=0.95,
                end_date="2026-04-21",
                live_game_context="NBA Tue, April 21st at 7:00 PM EDT; start 2026-04-21T23:00Z",
                live_match_confidence=0.85,
                live_match_reason="direct_match",
                resolvability="sports game outcome; verify live score and market rules",
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Lakers vs. Rockets",
                question="Lakers vs. Rockets",
                url="https://polymarket.com/event/nba-lal-hou-2026-04-24",
                outcome_prices=[("Lakers", 0.26), ("Rockets", 0.74)],
                engagement=_engagement(volume=20_000, liquidity=19_000),
                market_type="game_outcome",
                market_signal_quality=0.63,
                volume_24h=20_000,
                spread=0.01,
                relevance=0.92,
                end_date="2026-04-25",
                resolvability="sports game outcome; verify live score and market rules",
            ),
            schema.PolymarketItem(
                id="PM4",
                title="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                question="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-spurs-vs-trail-blazers",
                outcome_prices=[("Spurs", 0.96), ("Blazers", 0.04)],
                engagement=_engagement(volume=3_000, liquidity=29_000),
                market_type="futures",
                market_signal_quality=0.52,
                volume_24h=3_000,
                spread=0.02,
                relevance=0.95,
                end_date="2026-05-04",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report, limit=3)

        self.assertEqual([item.source_item_id for item in items], ["PM1", "PM2", "PM3"])


class EffectivelySettledWatchlistTests(unittest.TestCase):
    def test_effectively_settled_esports_market_is_rejected_from_generic_watchlist(self):
        report = _report("eSports markets today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM_PIN",
                title="LoL: Cloud9 vs Sentinels, Game 2 Winner",
                question="LoL: Cloud9 vs Sentinels, Game 2 Winner",
                url="https://polymarket.com/event/lol-c9-sen-2026-04-21",
                outcome_prices=[("Cloud9", 0.0), ("Sentinels", 1.0)],
                engagement=_engagement(volume=948_000, liquidity=244_000),
                market_type="game_outcome",
                market_signal_quality=0.78,
                volume_24h=948_000,
                best_bid=0.99,
                best_ask=1.00,
                spread=0.005,
                movement_24h=70.5,
                relevance=0.92,
                score=95,
            )
        ]

        self.assertEqual(market_watchlist.synthesize_market_watchlist(report), [])

    def test_effectively_settled_helper_catches_bottom_pin_too(self):
        item = schema.PolymarketItem(
            id="PM_BOT",
            title="Sentinels vs Cloud9",
            question="Sentinels vs Cloud9",
            url="https://polymarket.com/event/lol-sen-c9-2026-04-21",
            outcome_prices=[("Sentinels", 1.0), ("Cloud9", 0.005)],
            spread=0.008,
        )
        self.assertTrue(market_watchlist._item_effectively_settled(item))

    def test_live_game_watchlist_keeps_pinned_market_when_closing_mode_live(self):
        report = _report("live sports games on Polymarket right now")
        report.planning_notes = ["live-games:nba=1"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM_LIVE",
                title="Phoenix Suns vs Oklahoma City Thunder",
                question="Phoenix Suns vs Oklahoma City Thunder",
                url="https://polymarket.com/event/nba-phx-okc-2026-04-21",
                outcome_prices=[("Phoenix Suns", 0.005), ("Oklahoma City Thunder", 0.995)],
                engagement=_engagement(volume=500_000, liquidity=200_000),
                market_type="game_outcome",
                market_signal_quality=0.88,
                volume_24h=500_000,
                best_bid=0.994,
                best_ask=0.996,
                spread=0.002,
                movement_24h=5.0,
                closing_soon_reason="live_sports",
                minutes_to_close=30.0,
                live_game_context="Q4 3:45 — OKC 108, PHX 74",
                live_game_league="nba",
                live_match_confidence=0.95,
                live_match_reason="team + league match",
                resolvability="sports game outcome; verify live score and market rules",
                relevance=0.94,
                score=90,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_item_id, "PM_LIVE")

    def test_high_movement_non_pinned_esports_market_still_surfaces(self):
        report = _report("Counter-Strike 2 markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM_MOVING",
                title="Counter-Strike: Vitality vs NAVI (BO3) - IEM Katowice",
                question="Counter-Strike: Vitality vs NAVI (BO3) - IEM Katowice",
                url="https://polymarket.com/event/cs2-vit-navi-2026-04-21",
                outcome_prices=[("Vitality", 0.12), ("NAVI", 0.88)],
                engagement=_engagement(volume=400_000, liquidity=160_000),
                market_type="game_outcome",
                market_signal_quality=0.80,
                volume_24h=400_000,
                best_bid=0.87,
                best_ask=0.89,
                spread=0.02,
                movement_24h=18.0,
                relevance=0.92,
                score=88,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_item_id, "PM_MOVING")


if __name__ == "__main__":
    unittest.main()
