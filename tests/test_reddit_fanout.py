import unittest
from unittest import mock

from scripts import last24hours


class RedditFanoutPartialResultsTests(unittest.TestCase):
    def test_one_subquery_failure_does_not_discard_other_subquery_items(self):
        def fake_search(topic, config, selected_models, from_date, to_date, depth, mock_flag):
            if topic == "slow_topic":
                raise RuntimeError("per-topic failure")
            return (
                [{"topic": topic, "title": f"post from {topic}"}],
                {"topic": topic, "response": "ok"},
                None,
                False,
            )

        with mock.patch.object(last24hours, "_search_reddit", side_effect=fake_search):
            items, raw, err, used_sc = last24hours._search_reddit_many(
                ["fast_a", "slow_topic", "fast_b"],
                config={},
                selected_models={},
                from_date="2026-04-20",
                to_date="2026-04-21",
                depth="default",
                mock=False,
                total_budget_seconds=60,
            )

        # Partial merge should preserve the two fast topics even though slow_topic failed.
        topics_seen = {item["topic"] for item in items}
        self.assertEqual(topics_seen, {"fast_a", "fast_b"})
        # merged_error stays None whenever at least one topic returned results.
        self.assertIsNone(err)
        self.assertFalse(used_sc)
        # merged_raw records the successful topics.
        response_topics = {entry["topic"] for entry in raw["queries"]}
        self.assertEqual(response_topics, {"fast_a", "fast_b"})

    def test_all_subqueries_failing_reports_merged_error(self):
        def always_fail(topic, config, selected_models, from_date, to_date, depth, mock_flag):
            raise RuntimeError(f"{topic}: boom")

        with mock.patch.object(last24hours, "_search_reddit", side_effect=always_fail):
            items, _raw, err, _ = last24hours._search_reddit_many(
                ["a", "b"],
                config={},
                selected_models={},
                from_date="2026-04-20",
                to_date="2026-04-21",
                depth="default",
                mock=False,
                total_budget_seconds=60,
            )

        self.assertEqual(items, [])
        self.assertIsNotNone(err)
        self.assertIn("RuntimeError", err)

    def test_per_worker_timeout_floor_is_at_least_20_seconds(self):
        # With 10 topics and a 60s budget, naive division gives 6s — we clamp to 20s.
        captured = {}

        def fake_search(topic, config, selected_models, from_date, to_date, depth, mock_flag):
            return ([], {}, None, False)

        # Monkeypatch Future.result to capture the timeout kwarg that was applied.
        original_result = last24hours.ThreadPoolExecutor  # keep reference

        class RecordingFuture:
            def __init__(self, value):
                self._value = value

            def result(self, timeout=None):
                captured["timeout"] = timeout
                return self._value

            def cancel(self):
                return True

        def recording_as_completed(futures, timeout=None):
            for fut in list(futures):
                yield fut

        class RecordingPool:
            def __init__(self, max_workers=1):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, fn, *args, **kwargs):
                return RecordingFuture(fn(*args, **kwargs))

        with mock.patch.object(last24hours, "_search_reddit", side_effect=fake_search), \
             mock.patch.object(last24hours, "ThreadPoolExecutor", RecordingPool), \
             mock.patch.object(last24hours, "as_completed", recording_as_completed):
            last24hours._search_reddit_many(
                [f"topic_{i}" for i in range(10)],
                config={},
                selected_models={},
                from_date="2026-04-20",
                to_date="2026-04-21",
                depth="default",
                mock=False,
                total_budget_seconds=60,
            )

        self.assertIsNotNone(captured.get("timeout"))
        self.assertGreaterEqual(captured["timeout"], 20.0)


if __name__ == "__main__":
    unittest.main()
