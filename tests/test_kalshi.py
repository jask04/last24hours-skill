import unittest
from unittest import mock

from scripts import last24hours
from scripts.lib import forecast, kalshi, schema


class KalshiTests(unittest.TestCase):
    def test_nba_matchup_topic_detects_nba_series_search(self):
        self.assertIn("KXNBAGAME", kalshi._series_for_topic("76ers vs. Celtics"))

    def test_fed_cut_topic_detects_fed_macro_series_search(self):
        series = kalshi._series_for_topic("Fed rate cut by June")
        self.assertIn("KXFEDDECISION", series)
        self.assertIn("KXFED", series)

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
