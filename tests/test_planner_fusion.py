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
        report.reddit = [
            schema.RedditItem(
                id="R1",
                title="Game Thread: Portland Trail Blazers vs San Antonio Spurs Live Score | NBA Playoffs | Apr 19, 2026",
                url="https://reddit.com/r/nba/comments/old",
                subreddit="nba",
                score=90,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")
        self.assertIn("date-compatible", forecasts[0].degraded_warning)
        self.assertNotIn("threshold-compatible", forecasts[0].degraded_warning)
        self.assertNotIn("Apr 19", forecasts[0].why_line)

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

    def test_generic_sports_preview_does_not_become_why_line(self):
        report = _report("Raptors vs Cavaliers April 20 2026 Game 2")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Raptors", 0.24), ("Cavaliers", 0.76)],
                engagement=schema.Engagement(volume=50_000, liquidity=20_000),
                market_type="game_outcome",
                end_date="2026-04-20",
                score=90,
                relevance=0.90,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Toronto Raptors vs Cleveland Cavaliers 2026 playoffs: Will the Raptors' new lineup overpower the Cavs' defense? Discover the key matchups and strategies.",
                url="https://x.com/seo/status/1",
                author_handle="PreviewBot",
                score=99,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertNotIn("overpower", forecasts[0].why_line)
        self.assertIn("Mostly market-driven", forecasts[0].why_line)

    def test_real_injury_signal_beats_higher_scored_preview(self):
        report = _report("Raptors vs Cavaliers April 20 2026 Game 2")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Raptors", 0.24), ("Cavaliers", 0.76)],
                engagement=schema.Engagement(volume=50_000, liquidity=20_000),
                market_type="game_outcome",
                end_date="2026-04-20",
                score=90,
                relevance=0.90,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Toronto Raptors vs Cleveland Cavaliers preview: key matchups, strategy, tickets and TV channel.",
                url="https://x.com/seo/status/1",
                author_handle="PreviewBot",
                score=99,
            ),
            schema.XItem(
                id="X2",
                text="Raptors vs Cavaliers status report: Donovan Mitchell available, Thomas Bryant ruled out with calf injury.",
                url="https://x.com/reporter/status/2",
                author_handle="CavsBeatReporter",
                score=40,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("status report", forecasts[0].why_line)
        self.assertIn("ruled out", forecasts[0].why_line)
        self.assertNotIn("tickets", forecasts[0].why_line)

    def test_ticket_and_betting_bot_posts_are_rejected_from_sports_rationale(self):
        report = _report("Lakers vs Warriors April 20 2026 Game 2")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Lakers vs. Warriors",
                question="Lakers vs. Warriors",
                url="https://polymarket.com/event/nba-lal-gsw-2026-04-20",
                outcome_prices=[("Lakers", 0.58), ("Warriors", 0.42)],
                engagement=schema.Engagement(volume=50_000, liquidity=20_000),
                market_type="game_outcome",
                end_date="2026-04-20",
                score=90,
                relevance=0.90,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Selling Lakers Warriors tickets section 117 row 6 DM me",
                url="https://x.com/tickets/status/1",
                author_handle="ticketseller",
                score=99,
            ),
            schema.XItem(
                id="X2",
                text="BettorBot lock pick parlay Lakers Warriors tail this now",
                url="https://x.com/bot/status/2",
                author_handle="BettorBot",
                score=90,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertNotIn("tickets", forecasts[0].why_line.lower())
        self.assertNotIn("bettorbot", forecasts[0].why_line.lower())
        self.assertIn("Mostly market-driven", forecasts[0].why_line)

    def test_exact_date_sportsbook_odds_copy_is_rejected_from_sports_rationale(self):
        report = _report("Lakers vs Rockets April 21 2026 Game 2")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Rockets vs. Lakers",
                question="Rockets vs. Lakers",
                url="https://polymarket.com/event/nba-hou-lal-2026-04-21",
                outcome_prices=[("Rockets", 0.62), ("Lakers", 0.38)],
                engagement=schema.Engagement(volume=94_000, liquidity=324_000),
                market_type="game_outcome",
                end_date="2026-04-21",
                score=91,
                relevance=0.91,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="NBA playoff odds for Los Angeles Lakers vs Houston Rockets Game 2 betting, with point spread, moneyline, over/under for Tuesday, April 21, 2026.",
                url="https://x.com/azcentral/status/1",
                author_handle="azcentral",
                score=75,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.62)
        self.assertIn("Mostly market-driven", forecasts[0].why_line)
        self.assertNotIn("betting", forecasts[0].why_line.lower())
        self.assertNotIn("odds", forecasts[0].why_line.lower())

    def test_exact_date_line_movement_can_explain_matching_game(self):
        report = _report("Lakers vs Rockets April 21 2026 Game 2")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Rockets vs. Lakers",
                question="Rockets vs. Lakers",
                url="https://polymarket.com/event/nba-hou-lal-2026-04-21",
                outcome_prices=[("Rockets", 0.62), ("Lakers", 0.38)],
                engagement=schema.Engagement(volume=94_000, liquidity=324_000),
                market_type="game_outcome",
                end_date="2026-04-21",
                score=91,
                relevance=0.91,
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Los Angeles Lakers vs Houston Rockets Game 2 line moved toward Houston after Tuesday, April 21, 2026 lineup news.",
                url="https://x.com/reporter/status/1",
                author_handle="linewatch",
                score=75,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertIn("line moved", forecasts[0].why_line)
        self.assertNotIn("betting", forecasts[0].why_line.lower())

    def test_macro_alert_spam_does_not_become_why_line(self):
        report = _report("Fed rate cut by June")
        report.x = [
            schema.XItem(
                id="X1",
                text="🚨 BREAKING: FED HOLDS RATES HIGHER FOR LONGER AND TOP TRADERS ARE ALL OVER THIS MOVE RIGHT NOW.",
                url="https://x.com/spam/status/1",
                author_handle="spamdesk",
                score=95,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("no high-signal macro or policy evidence", forecasts[0].why_line.lower())
        self.assertNotIn("breaking", forecasts[0].why_line.lower())
        self.assertNotIn("top traders", forecasts[0].why_line.lower())

    def test_clean_macro_context_still_passes(self):
        report = _report("Fed rate cut by June")
        report.x = [
            schema.XItem(
                id="X1",
                text="Fed Governor remarks after CPI and jobs data kept June cut pricing soft in Treasury yields.",
                url="https://x.com/macro/status/1",
                author_handle="macrodesk",
                score=72,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("Fed Governor remarks", forecasts[0].why_line)

    def test_crypto_betting_big_and_poll_chatter_do_not_become_why_line(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="Six months ago most people were betting big on Bitcoin hitting $100K this year odds were above 60%. Quick BTC poll: vote A or B.",
                url="https://x.com/crypto/status/1",
                author_handle="cryptopromo",
                score=90,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("supporting evidence is thin", forecasts[0].why_line.lower())
        self.assertNotIn("betting big", forecasts[0].why_line.lower())
        self.assertNotIn("poll", forecasts[0].why_line.lower())

    def test_clean_crypto_market_context_still_passes(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="Bitcoin spot price stayed below 100k as ETF flows cooled and exchange liquidity thinned into the weekly close.",
                url="https://x.com/crypto/status/2",
                author_handle="flowdesk",
                score=78,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("ETF flows", forecasts[0].why_line)

    def test_macro_social_pricing_color_does_not_lead_model_implied_why_line(self):
        report = _report("Fed rate cut by June")
        report.x = [
            schema.XItem(
                id="X1",
                text="Fed June cut pricing still sits near one move, but the market is priced for two by year-end after yields softened.",
                url="https://x.com/macro/status/3",
                author_handle="macrocolor",
                score=90,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("no high-signal macro or policy evidence", forecasts[0].why_line.lower())
        self.assertEqual(report.evidence_fusion_stats["debug_counters"]["macro_social_demoted"], 1)

    def test_render_compact_suppresses_weak_crypto_x_chatter(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="Bitcoin is still the main character and the narrative feels strong again.",
                url="https://x.com/crypto/status/5",
                author_handle="narrativeguy",
                score=55,
            )
        ]
        report.forecasts = forecast.synthesize_forecasts(report)

        output = render.render_compact(report)

        self.assertIn("No high-signal X posts found for this crypto forecast.", output)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["crypto_opinion_demoted"], 1)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["source_row_suppressed"], 1)

    def test_render_compact_suppresses_crypto_threshold_chatter_without_threshold_match(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="@VohnJ43 @DragnonHD @GoingParabolic I appreciate the dialogue and I am rooting for that space + Bitcoin. I'm wary of the underlying tech right now, but maybe the next leg is coming.",
                url="https://x.com/crypto/status/6",
                author_handle="ReardonTrades",
                score=27,
            )
        ]
        report.forecasts = forecast.synthesize_forecasts(report)

        output = render.render_compact(report)

        self.assertIn("No high-signal X posts found for this crypto forecast.", output)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["crypto_opinion_demoted"], 1)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["source_row_suppressed"], 1)

    def test_render_compact_suppresses_crypto_threshold_etf_chatter_without_market_structure(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="@VohnJ43 @DragnonHD @GoingParabolic I appreciate the dialogue and I am rooting for that space + Bitcoin. We waited years for the spot ETFs in the U.S. and it blows my mind more folks didn't cash out above the mythical $100k.",
                url="https://x.com/crypto/status/61",
                author_handle="ReardonTrades",
                score=27,
            )
        ]
        report.forecasts = forecast.synthesize_forecasts(report)

        output = render.render_compact(report)

        self.assertIn("No high-signal X posts found for this crypto forecast.", output)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["crypto_opinion_demoted"], 1)
        self.assertGreaterEqual(report.evidence_fusion_stats["debug_counters"]["source_row_suppressed"], 1)

    def test_degraded_crypto_reranks_clean_source_rows_ahead_of_promo_noise(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="Most popular bets keep cashing and this quick BTC poll is everywhere.",
                url="https://x.com/crypto/status/3",
                author_handle="cryptopromo",
                score=95,
            ),
            schema.XItem(
                id="X2",
                text="Bitcoin spot price stayed below 100k as ETF flows cooled and exchange liquidity thinned into the weekly close.",
                url="https://x.com/crypto/status/4",
                author_handle="flowdesk",
                score=78,
            ),
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertIn("ETF flows", forecasts[0].why_line)
        self.assertEqual(report.x[0].id, "X2")

    def test_degraded_crypto_reranks_threshold_mismatch_social_row_below_threshold_match(self):
        report = _report("Bitcoin above 100k this week")
        report.x = [
            schema.XItem(
                id="X1",
                text="Bitcoin spot price held near 96k as ETF flows and exchange liquidity steadied into the weekly close.",
                url="https://x.com/crypto/status/7",
                author_handle="desk1",
                score=90,
            ),
            schema.XItem(
                id="X2",
                text="Bitcoin spot price stayed below 100k as ETF flows cooled and exchange liquidity thinned into the weekly close.",
                url="https://x.com/crypto/status/8",
                author_handle="desk2",
                score=78,
            ),
        ]

        forecast.synthesize_forecasts(report)

        self.assertEqual(report.x[0].id, "X2")

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
