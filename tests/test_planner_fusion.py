import unittest

from scripts.lib import evidence_fusion, forecast, forecast_plan, query_type, render, schema, sports_schedule


def _report(topic: str) -> schema.Report:
    return schema.Report(
        topic=topic,
        range_from="2026-04-10",
        range_to="2026-04-11",
        generated_at="2026-04-11T00:00:00+00:00",
        mode="both",
    )


class PlannerFusionTests(unittest.TestCase):
    def test_prediction_planner_is_market_first_and_quick_is_deterministic(self):
        plan = forecast_plan.build_plan(
            "Will the Fed cut rates by June",
            "prediction",
            "quick",
            web_backend="openrouter",
        )

        self.assertGreater(plan.source_weights["kalshi"], plan.source_weights["x"])
        self.assertGreater(plan.source_weights["polymarket"], plan.source_weights["reddit"])
        self.assertIn("quick-no-entity-resolution", plan.notes)
        self.assertLessEqual(len(plan.subqueries), 3)

    def test_watchlist_planner_uses_topic_scoped_market_queries(self):
        plan = forecast_plan.build_plan(
            "NBA markets to watch today",
            "market_watchlist",
            "quick",
        )

        self.assertEqual(plan.search_topics[0], "NBA")
        self.assertGreater(plan.source_weights["kalshi"], plan.source_weights["web"])

    def test_slate_plan_preserves_matchup_names(self):
        plan = forecast_plan.build_plan(
            "tomorrows nba games",
            "prediction",
            "quick",
            search_topics=["Los Angeles Lakers at Golden State Warriors", "Boston Celtics at New York Knicks"],
        )

        self.assertIn("Los Angeles Lakers at Golden State Warriors", plan.search_topics)
        self.assertIn("Boston Celtics at New York Knicks", plan.search_topics)

    def test_nba_matchups_tomorrow_counts_as_slate_query(self):
        self.assertTrue(sports_schedule.is_nba_slate_query("Last24hours NBA matchups tomorrow"))

    def test_fusion_prefers_injury_signal_over_ticket_chatter(self):
        report = _report("Lakers at Warriors tomorrow")
        report.x = [
            schema.XItem(
                id="X1",
                text="Selling Lakers Warriors tickets section 117 row 6 DM me",
                url="https://x.com/a/status/1",
                author_handle="ticketseller",
                score=99,
            ),
            schema.XItem(
                id="X2",
                text="Lakers Warriors injury update: starting lineup still questionable with two players ruled out",
                url="https://x.com/b/status/2",
                author_handle="beatreporter",
                score=40,
            ),
        ]

        result = evidence_fusion.fuse_evidence(report, report.topic, "prediction")

        self.assertTrue(result.drivers)
        self.assertIn("injury update", result.drivers[0].text)
        self.assertNotIn("tickets", result.drivers[0].text.lower())

    def test_fusion_caps_repeated_authors(self):
        report = _report("Will the Fed cut rates by June")
        report.x = [
            schema.XItem(
                id=f"X{i}",
                text=f"Fed rate cut odds moved after CPI inflation jobs data release {i}",
                url=f"https://x.com/bot/status/{i}",
                author_handle="macrobot",
                score=90 - i,
            )
            for i in range(4)
        ]
        report.web = [
            schema.WebSearchItem(
                id="W1",
                title="Fed rate-cut odds shift after CPI",
                url="https://example.com/fed",
                source_domain="example.com",
                snippet="CPI inflation data changed market-implied rate cut expectations for June.",
                score=50,
            )
        ]

        result = evidence_fusion.fuse_evidence(report, report.topic, "prediction", limit=4)
        macrobot_count = sum(1 for driver in result.drivers if driver.author_key == "x:macrobot")

        self.assertLessEqual(macrobot_count, 2)
        self.assertGreaterEqual(result.candidate_count, 4)

    def test_forecast_probability_remains_market_anchored_when_social_conflicts(self):
        report = _report("Lakers at Warriors tomorrow")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Lakers vs. Warriors",
                question="Lakers vs. Warriors",
                url="https://polymarket.com/event/nba-lal-gsw",
                outcome_prices=[("Lakers", 0.72), ("Warriors", 0.28)],
                engagement=schema.Engagement(volume=1_000_000, liquidity=300_000),
                market_type="game_outcome",
                score=95,
                relevance=0.95,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Warriors injury update improved: starting lineup available, Lakers rest concern",
                url="https://x.com/reporter/status/1",
                author_handle="reporter",
                score=95,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.72)
        self.assertEqual(forecasts[0].anchor_source, "polymarket")

    def test_sports_forecast_rejects_wrong_date_market(self):
        report = _report("Trail Blazers vs Spurs April 21 2026 Game 2")
        report.generated_at = "2026-04-20T12:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-19",
                outcome_prices=[("Spurs", 0.86), ("Trail Blazers", 0.14)],
                engagement=schema.Engagement(volume=1_000_000, liquidity=300_000),
                market_type="game_outcome",
                end_date="2026-04-19",
                score=99,
                relevance=0.99,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-21",
                outcome_prices=[("Spurs", 0.78), ("Trail Blazers", 0.22)],
                engagement=schema.Engagement(volume=100_000, liquidity=50_000),
                market_type="game_outcome",
                end_date="2026-04-21",
                score=70,
                relevance=0.70,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM2")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.78)

    def test_sports_forecast_falls_back_when_only_wrong_date_market_exists(self):
        report = _report("Trail Blazers vs Spurs April 21 2026 Game 2")
        report.generated_at = "2026-04-20T12:00:00+00:00"
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Trail Blazers vs. Spurs",
                question="Trail Blazers vs. Spurs",
                url="https://polymarket.com/event/nba-por-sas-2026-04-19",
                outcome_prices=[("Spurs", 0.86), ("Trail Blazers", 0.14)],
                engagement=schema.Engagement(volume=1_000_000, liquidity=300_000),
                market_type="game_outcome",
                end_date="2026-04-19",
                score=99,
                relevance=0.99,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")
        self.assertIn("date-compatible", forecasts[0].degraded_warning)
        self.assertNotIn("threshold-compatible", forecasts[0].degraded_warning)

    def test_slate_forecast_does_not_use_other_matchup_driver(self):
        report = _report("NBA matchups tomorrow")
        report.planning_notes = ["nba-slate-date:2026-04-20"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Hawks vs. Knicks",
                question="Hawks vs. Knicks",
                url="https://polymarket.com/event/nba-atl-nyk-2026-04-20",
                outcome_prices=[("Hawks", 0.32), ("Knicks", 0.68)],
                engagement=schema.Engagement(volume=100_000, liquidity=50_000),
                market_type="game_outcome",
                end_date="2026-04-20",
                score=90,
                relevance=0.90,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Minnesota Timberwolves status report for tomorrow at Denver Nuggets: QUESTIONABLE Anthony Edwards right knee injury maintenance",
                url="https://x.com/twolves/status/1",
                author_handle="Twolves_PR",
                score=95,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertNotIn("Timberwolves", forecasts[0].why_line)
        self.assertNotIn("Edwards", forecasts[0].why_line)

    def test_date_specific_macro_forecast_prefers_matching_month_market(self):
        report = _report("Will the Fed cut rates by June")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Fed rate cut by April 2026 meeting?",
                question="Will the Fed cut rates by the April 2026 meeting?",
                url="https://polymarket.com/event/fed-rate-cut-april",
                outcome_prices=[("Yes", 0.01), ("No", 0.99)],
                engagement=schema.Engagement(volume=2_000_000, liquidity=500_000),
                market_type="macro_binary",
                score=99,
                relevance=0.99,
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Fed rate cut by June 2026 meeting?",
                question="Will the Fed cut rates by the June 2026 meeting?",
                url="https://polymarket.com/event/fed-rate-cut-june",
                outcome_prices=[("Yes", 0.35), ("No", 0.65)],
                engagement=schema.Engagement(volume=100_000, liquidity=50_000),
                market_type="macro_binary",
                score=70,
                relevance=0.80,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM2")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.65)

    def test_fed_forecast_does_not_anchor_on_ecb_month_match(self):
        report = _report("Will the Fed cut rates by June")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="ECB Interest Rates: June 2026",
                question="Will the ECB announce a 50+ bps increase at the June 2026 meeting?",
                url="https://polymarket.com/event/ecb-interest-rates-june-2026",
                outcome_prices=[("Yes", 0.45), ("No", 0.55)],
                engagement=schema.Engagement(volume=1_000_000, liquidity=250_000),
                market_type="macro_binary",
                score=99,
                relevance=0.99,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")

    def test_date_specific_macro_forecast_suppresses_adjacent_month_market(self):
        report = _report("Will the Fed cut rates by June")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Fed rate cut by April 2026 meeting?",
                question="Will the Fed cut rates by the April 2026 meeting?",
                url="https://polymarket.com/event/fed-rate-cut-april",
                outcome_prices=[("Yes", 0.01), ("No", 0.99)],
                engagement=schema.Engagement(volume=2_000_000, liquidity=500_000),
                market_type="macro_binary",
                score=99,
                relevance=0.99,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")

    def test_compact_render_suppresses_unused_prediction_markets(self):
        report = _report("Will the Fed cut rates by June")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Fed rate cut by April 2026 meeting?",
                question="Will the Fed cut rates by the April 2026 meeting?",
                url="https://polymarket.com/event/fed-rate-cut-april",
                outcome_prices=[("Yes", 0.01), ("No", 0.99)],
                market_type="macro_binary",
                score=99,
                relevance=0.99,
            )
        ]
        report.forecasts = [
            schema.ForecastItem(
                title=report.topic,
                anchor_source="model_implied",
                market_view="No clean Polymarket or Kalshi market found.",
            )
        ]

        output = render.render_compact(report)

        self.assertIn("No Polymarket markets shown because none cleared forecast-anchor matching", output)
        self.assertNotIn("Will the Fed cut rates by the April 2026 meeting?", output)

    def test_compact_render_keeps_used_prediction_market(self):
        report = _report("Will the Fed cut rates by June")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Fed rate cut by June 2026 meeting?",
                question="Will the Fed cut rates by the June 2026 meeting?",
                url="https://polymarket.com/event/fed-rate-cut-june",
                outcome_prices=[("Yes", 0.35), ("No", 0.65)],
                market_type="macro_binary",
                score=90,
                relevance=0.90,
            )
        ]
        report.forecasts = [
            schema.ForecastItem(
                title=report.topic,
                anchor_source="polymarket",
                polymarket_market_id="PM1",
                market_view="Polymarket 65%",
            )
        ]

        output = render.render_compact(report)

        self.assertIn("Will the Fed cut rates by the June 2026 meeting?", output)
        self.assertNotIn("No Polymarket markets shown because none cleared", output)


if __name__ == "__main__":
    unittest.main()
