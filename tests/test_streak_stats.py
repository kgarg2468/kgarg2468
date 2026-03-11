import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate-contribution-graph.py"
SPEC = importlib.util.spec_from_file_location("generate_contribution_graph", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StreakStatsTests(unittest.TestCase):
    def compute(self, days, today):
        return MODULE.compute_streak_stats(days, total=123, local_today=today)

    def test_streak_constants(self):
        self.assertEqual(MODULE.STREAK_TIMEZONE, "America/Los_Angeles")
        self.assertEqual(MODULE.STREAK_TRAILING_ZERO_GRACE_DAYS, 2)

    def test_today_zero_yesterday_positive_continues(self):
        days = [
            ("2026-03-08", 1),
            ("2026-03-09", 2),
            ("2026-03-10", 1),
            ("2026-03-11", 0),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 3)

    def test_today_and_yesterday_zero_day_minus_two_positive_continues(self):
        days = [
            ("2026-03-08", 1),
            ("2026-03-09", 1),
            ("2026-03-10", 0),
            ("2026-03-11", 0),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 2)

    def test_three_trailing_zeros_allowed_when_grace_is_two(self):
        days = [
            ("2026-03-08", 1),
            ("2026-03-09", 0),
            ("2026-03-10", 0),
            ("2026-03-11", 0),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 1)

    def test_four_trailing_zeros_resets_streak(self):
        days = [
            ("2026-03-07", 1),
            ("2026-03-08", 0),
            ("2026-03-09", 0),
            ("2026-03-10", 0),
            ("2026-03-11", 0),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 0)

    def test_zero_after_streak_start_terminates_streak(self):
        days = [
            ("2026-03-07", 3),
            ("2026-03-08", 0),
            ("2026-03-09", 4),
            ("2026-03-10", 5),
            ("2026-03-11", 0),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 2)

    def test_future_dates_do_not_affect_streak(self):
        days = [
            ("2026-03-10", 1),
            ("2026-03-11", 0),
            ("2026-03-12", 9),
        ]
        _, current, _ = self.compute(days, today="2026-03-11")
        self.assertEqual(current, 1)

    def test_longest_streak_unchanged_by_trailing_zero_grace(self):
        days = [
            ("2026-03-01", 1),
            ("2026-03-02", 1),
            ("2026-03-03", 0),
            ("2026-03-04", 1),
            ("2026-03-05", 1),
            ("2026-03-06", 1),
            ("2026-03-07", 0),
            ("2026-03-08", 0),
            ("2026-03-09", 0),
            ("2026-03-10", 0),
        ]
        _, current, longest = self.compute(days, today="2026-03-10")
        self.assertEqual(current, 0)
        self.assertEqual(longest, 3)


if __name__ == "__main__":
    unittest.main()
