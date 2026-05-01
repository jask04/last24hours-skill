import unittest
from unittest import mock

from scripts import last24hours
from scripts.lib import forecast, kalshi, query_type, schema


class KalshiTests(unittest.TestCase):
    def test_nba_matchup_topic_detects_nba_series_search(self):
        self.assertIn("KXNBAGAME", kalshi._series_for_topic("76ers vs. Celtics"))

    def test_fed_cut_topic_detects_fed_macro_series_search(self):
        series = kalshi._series_for_topic("Fed rate cut by June")
        self.assertIn("KXFEDDECISION", series)
        self.assertIn("KXFED", series)

    def test_kalshi_live_board_topic_adds_broad_direct_series(self):
        series = kalshi._series_for_topic("Kalshi live markets")

        self.assertIn("KXBTC", series)
        self.assertIn("KXETH", series)
        self.assertIn("KXLLM1", series)
        self.assertIn("KXFEDDECISION", series)
        self.assertIn("KXCPI", series)
        self.assertIn("KXJOBS", series)
        self.assertIn("KXNBAGAME", series)

    def test_exchange_snapshot_query_detection_matches_live_board_aliases(self):
        self.assertTrue(query_type.is_exchange_snapshot_query("Kalshi markets right now", venue="kalshi"))
        self.assertTrue(query_type.is_exchange_snapshot_query("Kalshi markets now", venue="kalshi"))
        self.assertTrue(query_type.is_exchange_snapshot_query("Kalshi board right now", venue="kalshi"))
        self.assertTrue(query_type.is_exchange_snapshot_query("Polymarket board now", venue="polymarket"))

    def test_kalshi_closing_soon_topic_does_not_add_live_board_series(self):
        self.assertNotIn("KXNBAGAME", kalshi._series_for_topic("Kalshi markets closing soon"))

    def test_ai_and_golf_topics_route_to_live_kalshi_series(self):
        self.assertIn("KXLLM1", kalshi._series_for_topic("Best AI this week"))
        self.assertIn("KXCLAUDE", kalshi._series_for_topic("Claude markets"))
        self.assertIn("KXPGATOUR", kalshi._series_for_topic("Zurich Classic winner"))

    def test_kalshi_live_candidate_shortlist_keeps_series_diversity(self):
        ranked = [
            {"ticker": "KXFEDDECISION-26APR-H0", "event_ticker": "KXFEDDECISION-26APR"},
            {"ticker": "KXFEDDECISION-26APR-C25", "event_ticker": "KXFEDDECISION-26APR"},
            {"ticker": "KXFED-26APR-T3.75", "event_ticker": "KXFED-26APR"},
            {"ticker": "KXBTC-26APR2505-B77500", "event_ticker": "KXBTC-26APR2505"},
            {"ticker": "KXLLM1-26APR30-CLAUDE", "event_ticker": "KXLLM1-26APR30"},
        ]

        selected = kalshi._diverse_live_candidates(ranked, cap=2)
        selected_series = {row["ticker"].split("-", 1)[0] for row in selected[:4]}

        self.assertIn("KXFEDDECISION", selected_series)
        self.assertIn("KXFED", selected_series)
        self.assertIn("KXBTC", selected_series)
        self.assertIn("KXLLM1", selected_series)

    def test_kalshi_live_candidate_shortlist_keeps_quick_enrichment_bounded(self):
        ranked = [
            {"ticker": f"KXTEST{i}-26APR", "event_ticker": f"KXTEST{i}-26APR"}
            for i in range(20)
        ]

        selected = kalshi._diverse_live_candidates(ranked, cap=5)

        self.assertEqual(len(selected), 10)

    def test_search_kalshi_snapshot_uses_series_scan_and_skips_generic_first_page(self):
        series_markets = [
            {
                "ticker": "KXBTC-26MAY0117-B77250",
                "event_ticker": "KXBTC-26MAY0117",
                "title": "Bitcoin price range on May 1, 2026?",
                "subtitle": "Bitcoin price range on May 1, 2026?",
                "last_price_dollars": "0.48",
                "previous_price_dollars": "0.44",
                "yes_bid_dollars": "0.47",
                "yes_ask_dollars": "0.48",
                "open_interest_fp": "210000.00",
                "volume_24h_fp": "425000.00",
                "volume_fp": "600000.00",
                "liquidity_dollars": "120000.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-05-01T21:00:00Z",
                "status": "active",
            },
            {
                "ticker": "KXMVECROSSCATEGORY-S2026BAD",
                "event_ticker": "KXMVECROSSCATEGORY-S2026BAD",
                "title": "yes Team A,yes Team B,yes Team C",
                "subtitle": "crosscategory combo",
                "last_price_dollars": "0.60",
                "previous_price_dollars": "0.60",
                "yes_bid_dollars": "0.59",
                "yes_ask_dollars": "0.61",
                "open_interest_fp": "500000.00",
                "volume_24h_fp": "900000.00",
                "volume_fp": "950000.00",
                "liquidity_dollars": "200000.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-05-01T21:00:00Z",
                "status": "active",
            },
        ]

        with mock.patch.object(kalshi, "_fetch_markets_page", side_effect=AssertionError("generic first-page fetch should be skipped")), \
             mock.patch.object(kalshi, "_series_markets_for_topic", return_value=(series_markets, {"KXBTC-26MAY0117": "Bitcoin price range on May 1, 2026?"})), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", return_value={"event": {"title": "Bitcoin price range on May 1, 2026?"}}):
            response = kalshi.search_kalshi("Kalshi markets right now", "2026-04-30", "2026-05-01", depth="quick")
            parsed = kalshi.parse_kalshi_response(response, "Kalshi markets right now")

        self.assertEqual([row["ticker"] for row in parsed], ["KXBTC-26MAY0117-B77250"])

    def test_kalshi_snapshot_normalizes_double_space_titles(self):
        series_markets = [
            {
                "ticker": "KXBTC-26MAY0217-B77250",
                "event_ticker": "KXBTC-26MAY0217",
                "title": "Bitcoin price range  on May 2, 2026?",
                "subtitle": "Bitcoin price range  on May 2, 2026?",
                "last_price_dollars": "0.48",
                "previous_price_dollars": "0.44",
                "yes_bid_dollars": "0.47",
                "yes_ask_dollars": "0.48",
                "open_interest_fp": "210000.00",
                "volume_24h_fp": "425000.00",
                "volume_fp": "600000.00",
                "liquidity_dollars": "120000.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-05-02T21:00:00Z",
                "status": "active",
            },
        ]

        with mock.patch.object(kalshi, "_fetch_markets_page", side_effect=AssertionError("generic first-page fetch should be skipped")), \
             mock.patch.object(kalshi, "_series_markets_for_topic", return_value=(series_markets, {"KXBTC-26MAY0217": "Bitcoin price range  on May 2, 2026?"})), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", return_value={"event": {"title": "Bitcoin price range  on May 2, 2026?"}}):
            response = kalshi.search_kalshi("Kalshi markets right now", "2026-04-30", "2026-05-01", depth="quick")
            parsed = kalshi.parse_kalshi_response(response, "Kalshi markets right now")

        self.assertEqual(parsed[0]["title"], "Bitcoin price range on May 2, 2026?")
        self.assertEqual(parsed[0]["question"], "Bitcoin price range on May 2, 2026?")

    def test_search_kalshi_snapshot_prefers_nearer_term_active_rows_over_long_dated_macro(self):
        series_markets = [
            {
                "ticker": "KXFEDDECISION-26JUN-H0",
                "event_ticker": "KXFEDDECISION-26JUN",
                "title": "Will the Federal Reserve Hike rates by 0bps at their June 2026 meeting?",
                "subtitle": "Fed decision in Jun 2026?",
                "last_price_dollars": "0.95",
                "previous_price_dollars": "0.95",
                "yes_bid_dollars": "0.95",
                "yes_ask_dollars": "0.96",
                "open_interest_fp": "713841.06",
                "volume_24h_fp": "355329.10",
                "volume_fp": "800000.00",
                "liquidity_dollars": "0.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-06-17T21:00:00Z",
                "status": "active",
            },
            {
                "ticker": "KXBTC-26MAY0117-B77250",
                "event_ticker": "KXBTC-26MAY0117",
                "title": "Bitcoin price range on May 1, 2026?",
                "subtitle": "Bitcoin price range on May 1, 2026?",
                "last_price_dollars": "0.48",
                "previous_price_dollars": "0.44",
                "yes_bid_dollars": "0.47",
                "yes_ask_dollars": "0.48",
                "open_interest_fp": "210000.00",
                "volume_24h_fp": "425000.00",
                "volume_fp": "600000.00",
                "liquidity_dollars": "120000.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-05-01T21:00:00Z",
                "status": "active",
            },
            {
                "ticker": "KXETH-26MAY0204-B2260",
                "event_ticker": "KXETH-26MAY0204",
                "title": "Ethereum price at May 2, 2026 at 4am EDT?",
                "subtitle": "Ethereum price at May 2, 2026 at 4am EDT?",
                "last_price_dollars": "0.36",
                "previous_price_dollars": "0.31",
                "yes_bid_dollars": "0.35",
                "yes_ask_dollars": "0.36",
                "open_interest_fp": "95000.00",
                "volume_24h_fp": "120000.00",
                "volume_fp": "225000.00",
                "liquidity_dollars": "60000.00",
                "updated_time": "2026-05-01T06:00:00Z",
                "expiration_time": "2026-05-02T08:00:00Z",
                "status": "active",
            },
        ]

        with mock.patch.object(kalshi, "_fetch_markets_page", side_effect=AssertionError("generic first-page fetch should be skipped")), \
             mock.patch.object(
                 kalshi,
                 "_series_markets_for_topic",
                 return_value=(series_markets, {
                     "KXFEDDECISION-26JUN": "Fed decision in Jun 2026?",
                     "KXBTC-26MAY0117": "Bitcoin price range on May 1, 2026?",
                     "KXETH-26MAY0204": "Ethereum price at May 2, 2026 at 4am EDT?",
                 }),
             ), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", return_value={"event": {}}):
            response = kalshi.search_kalshi("Kalshi markets right now", "2026-04-30", "2026-05-01", depth="quick")

        self.assertEqual(response["markets"][0]["ticker"], "KXBTC-26MAY0117-B77250")
        self.assertNotEqual(response["markets"][0]["ticker"], "KXFEDDECISION-26JUN-H0")

    def test_series_markets_for_topic_snapshot_prefers_nearer_events_within_series(self):
        events_by_series = {
            "KXFEDDECISION": [
                {
                    "event_ticker": "KXFEDDECISION-27DEC",
                    "title": "Fed decision in Dec 2027?",
                    "available_on_brokers": True,
                    "strike_date": "2027-12-08T19:00:00Z",
                    "last_updated_ts": "2026-05-01T00:00:00Z",
                },
                {
                    "event_ticker": "KXFEDDECISION-26JUN",
                    "title": "Fed decision in Jun 2026?",
                    "available_on_brokers": True,
                    "strike_date": "2026-06-17T18:00:00Z",
                    "last_updated_ts": "2026-05-01T00:00:00Z",
                },
            ],
            "KXBTC": [
                {
                    "event_ticker": "KXBTC-26MAY0117",
                    "title": "Bitcoin price range on May 1, 2026 at 5pm EDT?",
                    "available_on_brokers": True,
                    "strike_date": "2026-05-01T21:00:00Z",
                    "last_updated_ts": "2026-05-01T00:00:00Z",
                }
            ],
        }
        markets_by_event = {
            "KXFEDDECISION-27DEC": [{"ticker": "KXFEDDECISION-27DEC-C25"}],
            "KXFEDDECISION-26JUN": [{"ticker": "KXFEDDECISION-26JUN-C25"}],
            "KXBTC-26MAY0117": [{"ticker": "KXBTC-26MAY0117-B77250"}],
        }

        with mock.patch.object(kalshi, "_series_for_topic", return_value=["KXFEDDECISION", "KXBTC"]), \
             mock.patch.object(kalshi, "_fetch_events_for_series", side_effect=lambda series_ticker, limit=8: events_by_series.get(series_ticker, [])), \
             mock.patch.object(kalshi, "_fetch_markets_for_event", side_effect=lambda event_ticker: markets_by_event[event_ticker]):
            markets, titles = kalshi._series_markets_for_topic("Kalshi markets right now", "quick")

        tickers = {market["ticker"] for market in markets}
        self.assertIn("KXFEDDECISION-26JUN-C25", tickers)
        self.assertNotIn("KXFEDDECISION-27DEC-C25", tickers)
        self.assertIn("KXBTC-26MAY0117-B77250", tickers)
        self.assertEqual(titles["KXFEDDECISION-26JUN"], "Fed decision in Jun 2026?")

    def test_search_kalshi_filters_nba_games_to_topic_day(self):
        events = [
            {
                "event_ticker": "KXNBAGAME-26APR21PHIBOS",
                "title": "Game 2: Philadelphia at Boston",
                "available_on_brokers": True,
                "last_updated_ts": "2026-04-21T00:00:00Z",
            },
            {
                "event_ticker": "KXNBAGAME-26APR23NYKATL",
                "title": "Game 3: New York at Atlanta",
                "available_on_brokers": True,
                "last_updated_ts": "2026-04-21T00:00:00Z",
            },
        ]
        markets_by_event = {
            "KXNBAGAME-26APR21PHIBOS": [{
                "ticker": "KXNBAGAME-26APR21PHIBOS-BOS",
                "event_ticker": "KXNBAGAME-26APR21PHIBOS",
                "title": "Game 2: Philadelphia at Boston Winner?",
                "last_price_dollars": "0.88",
                "previous_price_dollars": "0.86",
                "yes_bid_dollars": "0.87",
                "yes_ask_dollars": "0.88",
                "open_interest_fp": "120000.00",
                "volume_24h_fp": "150000.00",
                "volume_fp": "175000.00",
                "liquidity_dollars": "0.00",
                "updated_time": "2026-04-21T02:00:00Z",
                "expiration_time": "2026-05-07T23:00:00Z",
                "status": "active",
            }],
            "KXNBAGAME-26APR23NYKATL": [{
                "ticker": "KXNBAGAME-26APR23NYKATL-NYK",
                "event_ticker": "KXNBAGAME-26APR23NYKATL",
                "title": "Game 3: New York at Atlanta Winner?",
                "last_price_dollars": "0.51",
                "previous_price_dollars": "0.56",
                "yes_bid_dollars": "0.50",
                "yes_ask_dollars": "0.51",
                "open_interest_fp": "92085.14",
                "volume_24h_fp": "93126.58",
                "volume_fp": "107217.89",
                "liquidity_dollars": "0.00",
                "updated_time": "2026-04-21T02:00:00Z",
                "expiration_time": "2026-05-07T23:00:00Z",
                "status": "active",
            }],
        }

        with mock.patch.object(kalshi, "_fetch_markets_page", return_value={"markets": [], "cursor": None}), \
             mock.patch.object(kalshi, "_series_for_topic", return_value=["KXNBAGAME"]), \
             mock.patch.object(kalshi, "_fetch_events_for_series", return_value=events), \
             mock.patch.object(kalshi, "_fetch_markets_for_event", side_effect=lambda ticker: markets_by_event[ticker]), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", side_effect=lambda ticker: {"event": {"title": next(e["title"] for e in events if e["event_ticker"] == ticker)}}):
            response = kalshi.search_kalshi("NBA markets to watch today", "2026-04-20", "2026-04-21", depth="quick")

        self.assertEqual(len(response["markets"]), 1)
        self.assertEqual(response["markets"][0]["event_ticker"], "KXNBAGAME-26APR21PHIBOS")

    def test_kalshi_matchup_filter_accepts_nba_team_codes_for_matchup_topics(self):
        item = {
            "title": "Game 2: Phoenix at Oklahoma City",
            "question": "Game 2: Phoenix at Oklahoma City Winner?",
            "ticker": "KXNBAGAME-26APR22PHXOKC-OKC",
            "event_ticker": "KXNBAGAME-26APR22PHXOKC",
        }

        self.assertTrue(last24hours._market_matches_matchup(item, "Suns vs. Thunder"))

    def test_sports_market_date_compatible_reads_kalshi_compact_ticker_date(self):
        item = schema.KalshiItem(
            id="KA1",
            title="Game 3: New York at Atlanta",
            question="Game 3: New York at Atlanta Winner?",
            url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR23NYKATL-NYK",
            ticker="KXNBAGAME-26APR23NYKATL-NYK",
            event_ticker="KXNBAGAME-26APR23NYKATL",
            current_probability=0.51,
        )

        self.assertTrue(forecast._sports_market_date_compatible(item, "2026-04-23"))
        self.assertFalse(forecast._sports_market_date_compatible(item, "2026-04-21"))

    def test_search_kalshi_fed_cut_prefers_direct_decision_contracts(self):
        events = [
            {
                "event_ticker": "KXFEDDECISION-26APR",
                "title": "Fed decision in Apr 2026?",
                "available_on_brokers": True,
                "last_updated_ts": "2026-04-21T00:00:00Z",
            },
            {
                "event_ticker": "KXFEDDECISION-26JUN",
                "title": "Fed decision in Jun 2026?",
                "available_on_brokers": True,
                "last_updated_ts": "2026-04-21T00:00:00Z",
            },
        ]
        markets_by_event = {
            "KXFEDDECISION-26APR": [{
                "ticker": "KXFEDDECISION-26APR-C25",
                "event_ticker": "KXFEDDECISION-26APR",
                "title": "Will the Federal Reserve Cut rates by 25bps at their April 2026 meeting?",
                "last_price_dollars": "0.18",
                "previous_price_dollars": "0.20",
                "yes_bid_dollars": "0.17",
                "yes_ask_dollars": "0.18",
                "open_interest_fp": "100000.00",
                "volume_24h_fp": "10000.00",
                "volume_fp": "50000.00",
                "updated_time": "2026-04-21T02:00:00Z",
                "expiration_time": "2026-04-30T23:00:00Z",
                "status": "active",
            }],
            "KXFEDDECISION-26JUN": [
                {
                    "ticker": "KXFEDDECISION-26JUN-C25",
                    "event_ticker": "KXFEDDECISION-26JUN",
                    "title": "Will the Federal Reserve Cut rates by 25bps at their June 2026 meeting?",
                    "last_price_dollars": "0.42",
                    "previous_price_dollars": "0.40",
                    "yes_bid_dollars": "0.41",
                    "yes_ask_dollars": "0.42",
                    "open_interest_fp": "250000.00",
                    "volume_24h_fp": "150000.00",
                    "volume_fp": "600000.00",
                    "updated_time": "2026-04-21T02:00:00Z",
                    "expiration_time": "2026-06-18T23:00:00Z",
                    "status": "active",
                },
                {
                    "ticker": "KXFEDDECISION-26JUN-H25",
                    "event_ticker": "KXFEDDECISION-26JUN",
                    "title": "Will the Federal Reserve Hike rates by 25bps at their June 2026 meeting?",
                    "last_price_dollars": "0.08",
                    "previous_price_dollars": "0.10",
                    "yes_bid_dollars": "0.07",
                    "yes_ask_dollars": "0.08",
                    "open_interest_fp": "80000.00",
                    "volume_24h_fp": "10000.00",
                    "volume_fp": "20000.00",
                    "updated_time": "2026-04-21T02:00:00Z",
                    "expiration_time": "2026-06-18T23:00:00Z",
                    "status": "active",
                },
            ],
        }

        def fetch_events(series_ticker, limit=8):
            return events if series_ticker == "KXFEDDECISION" else []

        with mock.patch.object(kalshi, "_fetch_markets_page", return_value={"markets": [], "cursor": None}), \
             mock.patch.object(kalshi, "_series_for_topic", return_value=["KXFEDDECISION"]), \
             mock.patch.object(kalshi, "_fetch_events_for_series", side_effect=fetch_events), \
             mock.patch.object(kalshi, "_fetch_markets_for_event", side_effect=lambda ticker: markets_by_event[ticker]), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", side_effect=lambda ticker: {"event": {"title": next(e["title"] for e in events if e["event_ticker"] == ticker)}}):
            response = kalshi.search_kalshi("Fed rate cut by June", "2026-04-20", "2026-04-21", depth="quick")
            parsed = kalshi.parse_kalshi_response(response, "Fed rate cut by June")

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["ticker"], "KXFEDDECISION-26JUN-C25")
        self.assertEqual(parsed[0]["market_type"], "macro_binary")

    def test_search_kalshi_macro_month_filter_rejects_generic_adjacent_month_rows(self):
        events = [
            {
                "event_ticker": "KXFEDDECISION-26JUN",
                "title": "Fed decision in Jun 2026?",
                "available_on_brokers": True,
                "last_updated_ts": "2026-04-21T00:00:00Z",
            }
        ]
        generic_page = {
            "markets": [
                {
                    "ticker": "KXFEDDECISION-26APR-C25",
                    "event_ticker": "KXFEDDECISION-26APR",
                    "title": "Will the Federal Reserve Cut rates by 25bps at their April 2026 meeting?",
                    "last_price_dollars": "0.18",
                    "previous_price_dollars": "0.20",
                    "yes_bid_dollars": "0.17",
                    "yes_ask_dollars": "0.18",
                    "open_interest_fp": "100000.00",
                    "volume_24h_fp": "10000.00",
                    "volume_fp": "50000.00",
                    "updated_time": "2026-04-21T02:00:00Z",
                    "expiration_time": "2026-04-30T23:00:00Z",
                    "status": "active",
                }
            ],
            "cursor": None,
        }
        series_markets = {
            "KXFEDDECISION-26JUN": [{
                "ticker": "KXFEDDECISION-26JUN-C25",
                "event_ticker": "KXFEDDECISION-26JUN",
                "title": "Will the Federal Reserve Cut rates by 25bps at their June 2026 meeting?",
                "last_price_dollars": "0.42",
                "previous_price_dollars": "0.40",
                "yes_bid_dollars": "0.41",
                "yes_ask_dollars": "0.42",
                "open_interest_fp": "250000.00",
                "volume_24h_fp": "150000.00",
                "volume_fp": "600000.00",
                "updated_time": "2026-04-21T02:00:00Z",
                "expiration_time": "2026-06-18T23:00:00Z",
                "status": "active",
            }]
        }

        with mock.patch.object(kalshi, "_fetch_markets_page", return_value=generic_page), \
             mock.patch.object(kalshi, "_series_for_topic", return_value=["KXFEDDECISION"]), \
             mock.patch.object(kalshi, "_fetch_events_for_series", return_value=events), \
             mock.patch.object(kalshi, "_fetch_markets_for_event", side_effect=lambda ticker: series_markets[ticker]), \
             mock.patch.object(kalshi, "_apply_candlestick_signals", return_value=None), \
             mock.patch.object(kalshi, "_fetch_event", return_value={"event": {"title": "Fed decision in Jun 2026?"}}):
            response = kalshi.search_kalshi("Fed rate cut by June", "2026-04-20", "2026-04-21", depth="quick")
            parsed = kalshi.parse_kalshi_response(response, "Fed rate cut by June")

        self.assertEqual([row["ticker"] for row in parsed], ["KXFEDDECISION-26JUN-C25"])


if __name__ == "__main__":
    unittest.main()
