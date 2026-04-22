"""Regression tests for the sportsbook odds context tier (v1.0.54)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.lib import sportsbook


class OddsConversionTests(unittest.TestCase):
    def test_american_to_decimal_positive(self):
        # +150 → 2.50
        self.assertAlmostEqual(sportsbook.american_to_decimal(150), 2.50, places=4)

    def test_american_to_decimal_negative(self):
        # -175 → 1.5714
        self.assertAlmostEqual(sportsbook.american_to_decimal(-175), 1.5714, places=4)

    def test_american_to_decimal_even(self):
        self.assertAlmostEqual(sportsbook.american_to_decimal(100), 2.0, places=4)
        self.assertAlmostEqual(sportsbook.american_to_decimal(-100), 2.0, places=4)

    def test_american_to_implied_probability_favorite(self):
        # -175 → 63.64%
        self.assertAlmostEqual(
            sportsbook.american_to_implied_probability(-175), 0.6364, places=4
        )

    def test_american_to_implied_probability_underdog(self):
        # +140 → 41.67%
        self.assertAlmostEqual(
            sportsbook.american_to_implied_probability(140), 0.4167, places=4
        )

    def test_round_trip_decimal_matches_implied(self):
        # For any American price, decimal and implied-prob should be consistent:
        # decimal - 1 == (1 - implied) / implied  →  decimal * implied == 1
        for price in (-300, -175, -110, 100, 140, 250, 500):
            d = sportsbook.american_to_decimal(price)
            p = sportsbook.american_to_implied_probability(price)
            self.assertAlmostEqual(d * p, 1.0, places=3, msg=f"price={price}")


class SportDetectionTests(unittest.TestCase):
    def test_detect_nba_from_team(self):
        self.assertEqual(sportsbook.detect_sport("Lakers at Warriors tonight"), "nba")

    def test_detect_nfl_from_league(self):
        self.assertEqual(sportsbook.detect_sport("NFL Sunday slate"), "nfl")

    def test_detect_mlb_from_team(self):
        self.assertEqual(sportsbook.detect_sport("Yankees vs Red Sox tonight"), "mlb")

    def test_detect_nhl_from_team(self):
        # Use unambiguously-NHL teams; "Rangers" collides with MLB Texas Rangers.
        self.assertEqual(sportsbook.detect_sport("Oilers at Maple Leafs tonight"), "nhl")

    def test_unsupported_sport_returns_none(self):
        self.assertIsNone(sportsbook.detect_sport("Wimbledon final tomorrow"))

    def test_empty_topic_returns_none(self):
        self.assertIsNone(sportsbook.detect_sport(""))


class AvailabilityTests(unittest.TestCase):
    def test_no_api_key_means_unavailable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(sportsbook.is_available({}))

    def test_api_key_means_available(self):
        with mock.patch.dict(os.environ, {"ODDS_API_KEY": "abc123"}, clear=True):
            self.assertTrue(sportsbook.is_available({}))

    def test_disable_flag_overrides_api_key(self):
        with mock.patch.dict(
            os.environ,
            {"ODDS_API_KEY": "abc123", "LAST24HOURS_DISABLE_SPORTSBOOK": "1"},
            clear=True,
        ):
            self.assertFalse(sportsbook.is_available({}))

    def test_configured_books_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sportsbook.configured_books({}), sportsbook.DEFAULT_BOOKS)

    def test_configured_books_override(self):
        with mock.patch.dict(
            os.environ, {"LAST24HOURS_SPORTSBOOK_BOOKS": "fanduel, draftkings"}, clear=True
        ):
            self.assertEqual(
                sportsbook.configured_books({}), ("fanduel", "draftkings")
            )


class SearchSportsbookGracefulFallbackTests(unittest.TestCase):
    def test_missing_api_key_returns_error_payload_no_raise(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            response = sportsbook.search_sportsbook("Lakers at Warriors tonight", config={})
        self.assertEqual(response["events"], [])
        self.assertIn("ODDS_API_KEY", response["error"])

    def test_unsupported_sport_returns_error_without_http_call(self):
        with mock.patch.dict(os.environ, {"ODDS_API_KEY": "k"}, clear=True), \
             mock.patch.object(sportsbook.http, "get") as mock_get:
            response = sportsbook.search_sportsbook("Wimbledon final", config={})
        self.assertEqual(response["events"], [])
        self.assertIn("unsupported sport", response["error"])
        mock_get.assert_not_called()

    def test_http_error_captured_not_raised(self):
        with mock.patch.dict(os.environ, {"ODDS_API_KEY": "k"}, clear=True), \
             mock.patch.object(
                sportsbook.http, "get",
                side_effect=sportsbook.http.HTTPError("HTTP 429: Too Many Requests", status_code=429),
             ):
            with _temp_usage_file():
                response = sportsbook.search_sportsbook(
                    "Lakers at Warriors tonight", config={}
                )
        self.assertEqual(response["events"], [])
        self.assertIn("HTTPError", response["error"])

    def test_monthly_cap_short_circuits_before_http(self):
        with mock.patch.dict(os.environ, {"ODDS_API_KEY": "k"}, clear=True), \
             mock.patch.object(sportsbook.http, "get") as mock_get, \
             _temp_usage_file() as usage_path:
            # Pre-seed ledger at the cap
            usage_path.write_text(
                json.dumps({"month": sportsbook._current_month_key(), "count": sportsbook.MONTHLY_CAP + 1})
            )
            response = sportsbook.search_sportsbook("Lakers at Warriors tonight", config={})
        self.assertIn("monthly budget", response["error"])
        mock_get.assert_not_called()


class ParseSportsbookResponseTests(unittest.TestCase):
    def test_parses_h2h_event_into_per_outcome_quotes(self):
        raw = {
            "sport": "nba",
            "events": [
                {
                    "id": "evt1",
                    "home_team": "Golden State Warriors",
                    "away_team": "Los Angeles Lakers",
                    "commence_time": "2026-04-22T02:30:00Z",
                    "bookmakers": [
                        {
                            "key": "fanduel",
                            "last_update": "2026-04-21T19:05:00Z",
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [
                                        {"name": "Golden State Warriors", "price": -175},
                                        {"name": "Los Angeles Lakers", "price": 148},
                                    ],
                                },
                            ],
                        },
                        {
                            "key": "draftkings",
                            "last_update": "2026-04-21T19:06:00Z",
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [
                                        {"name": "Golden State Warriors", "price": -180},
                                        {"name": "Los Angeles Lakers", "price": 155},
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        items = sportsbook.parse_sportsbook_response(raw, topic="Lakers at Warriors")
        self.assertEqual(len(items), 4)  # 2 books x 2 outcomes
        books = {i["book"] for i in items}
        self.assertEqual(books, {"fanduel", "draftkings"})
        for i in items:
            self.assertEqual(i["market_type"], "moneyline")
            self.assertEqual(i["kind"], "sportsbook_quote")
            self.assertIn(i["event_key"], {
                "los-angeles-lakers-vs-golden-state-warriors-2026-04-22",
            })
            self.assertIsNone(i["line"])
            self.assertIsInstance(i["price_american"], int)
            self.assertIsInstance(i["price_decimal"], float)
            self.assertIsInstance(i["implied_probability"], float)

    def test_parses_spread_and_total_markets(self):
        raw = {
            "sport": "nba",
            "events": [
                {
                    "home_team": "Boston Celtics",
                    "away_team": "Miami Heat",
                    "commence_time": "2026-04-22T23:00:00Z",
                    "bookmakers": [
                        {
                            "key": "fanduel",
                            "last_update": "2026-04-21T19:05:00Z",
                            "markets": [
                                {
                                    "key": "spreads",
                                    "outcomes": [
                                        {"name": "Boston Celtics", "price": -110, "point": -6.5},
                                        {"name": "Miami Heat", "price": -110, "point": 6.5},
                                    ],
                                },
                                {
                                    "key": "totals",
                                    "outcomes": [
                                        {"name": "Over", "price": -115, "point": 218.5},
                                        {"name": "Under", "price": -105, "point": 218.5},
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        items = sportsbook.parse_sportsbook_response(raw, topic="Heat at Celtics")
        types = {i["market_type"] for i in items}
        self.assertEqual(types, {"spread", "total"})
        spreads = [i for i in items if i["market_type"] == "spread"]
        totals = [i for i in items if i["market_type"] == "total"]
        self.assertEqual({s["line"] for s in spreads}, {-6.5, 6.5})
        self.assertEqual({t["line"] for t in totals}, {218.5})

    def test_skips_malformed_outcomes_without_raising(self):
        raw = {
            "sport": "nba",
            "events": [
                {
                    "home_team": "A",
                    "away_team": "B",
                    "commence_time": "2026-04-22T00:00:00Z",
                    "bookmakers": [
                        {
                            "key": "fanduel",
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [
                                        {"name": "A", "price": "not-a-number"},
                                        {"name": "B", "price": -120},
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        items = sportsbook.parse_sportsbook_response(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["side"], "B")

    def test_empty_response_returns_empty_list(self):
        self.assertEqual(sportsbook.parse_sportsbook_response({"events": []}), [])
        self.assertEqual(sportsbook.parse_sportsbook_response({}), [])


class ConsensusRowsTests(unittest.TestCase):
    def test_collapses_multi_book_quotes_into_single_row(self):
        quotes = [
            {
                "event_key": "e1", "market_type": "moneyline", "side": "Lakers", "line": None,
                "price_american": 148, "book": "fanduel", "last_update": "t1",
                "implied_probability": 0.4032, "commence_time": "2026-04-22T02:30:00Z",
                "event_title": "Lakers @ Warriors", "sport": "nba",
            },
            {
                "event_key": "e1", "market_type": "moneyline", "side": "Lakers", "line": None,
                "price_american": 155, "book": "draftkings", "last_update": "t2",
                "implied_probability": 0.3922, "commence_time": "2026-04-22T02:30:00Z",
                "event_title": "Lakers @ Warriors", "sport": "nba",
            },
        ]
        rows = sportsbook.consensus_rows(quotes)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # Best price for the bettor = highest positive = +155 from DK
        self.assertEqual(row["best_price_american"], 155)
        self.assertEqual(row["worst_price_american"], 148)
        self.assertEqual({b["book"] for b in row["books"]}, {"fanduel", "draftkings"})


class UsageLedgerTests(unittest.TestCase):
    def test_record_api_call_increments(self):
        with _temp_usage_file():
            start, _ = sportsbook.current_month_usage()
            total = sportsbook.record_api_call(3)
            self.assertEqual(total, start + 3)

    def test_within_budget_true_when_empty(self):
        with _temp_usage_file():
            self.assertTrue(sportsbook.within_monthly_budget(reserve=1))

    def test_within_budget_false_at_cap(self):
        with _temp_usage_file() as usage_path:
            usage_path.write_text(
                json.dumps({"month": sportsbook._current_month_key(), "count": sportsbook.MONTHLY_CAP})
            )
            self.assertFalse(sportsbook.within_monthly_budget(reserve=1))


def _temp_usage_file():
    """Context manager that redirects the usage ledger to a tempfile."""
    class _Ctx:
        def __enter__(self):
            self.dir = tempfile.TemporaryDirectory()
            self.path = Path(self.dir.name) / "sportsbook_usage.json"
            self._orig = os.environ.get("LAST24HOURS_SPORTSBOOK_USAGE_FILE")
            os.environ["LAST24HOURS_SPORTSBOOK_USAGE_FILE"] = str(self.path)
            return self.path

        def __exit__(self, *args):
            if self._orig is None:
                os.environ.pop("LAST24HOURS_SPORTSBOOK_USAGE_FILE", None)
            else:
                os.environ["LAST24HOURS_SPORTSBOOK_USAGE_FILE"] = self._orig
            self.dir.cleanup()
            return False

    return _Ctx()


if __name__ == "__main__":
    unittest.main()
