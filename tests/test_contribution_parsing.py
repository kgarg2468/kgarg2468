import importlib.util
import unittest
from unittest import mock
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate-contribution-graph.py"
SPEC = importlib.util.spec_from_file_location("generate_contribution_graph", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REAL_DATETIME = MODULE.datetime


class ContributionParsingTests(unittest.TestCase):
    def test_scrape_contributions_parses_plain_yearly_total(self):
        html = """
        <h2 tabindex="-1" id="js-contribution-activity-description" class="f4 text-normal mb-2">
          206 contributions in 2025
        </h2>
        <td data-date="2025-12-31"></td><tool-tip>4 contributions on Dec 31.</tool-tip>
        """

        with mock.patch.object(MODULE, "fetch_contributions_html", return_value=html):
            day_counts, yearly_total = MODULE.scrape_contributions(2025)

        self.assertEqual(yearly_total, 206)
        self.assertEqual(day_counts["2025-12-31"], 4)

    def test_scrape_contributions_parses_comma_formatted_yearly_total(self):
        html = """
        <h2 tabindex="-1" id="js-contribution-activity-description" class="f4 text-normal mb-2">
          1,012 contributions in 2026
        </h2>
        <td data-date="2026-04-13"></td><tool-tip>7 contributions on Apr 13.</tool-tip>
        """

        with mock.patch.object(MODULE, "fetch_contributions_html", return_value=html):
            day_counts, yearly_total = MODULE.scrape_contributions(2026)

        self.assertEqual(yearly_total, 1012)
        self.assertEqual(day_counts["2026-04-13"], 7)

    def test_scrape_contributions_parses_multi_comma_yearly_total(self):
        html = """
        <h2 tabindex="-1" id="js-contribution-activity-description" class="f4 text-normal mb-2">
          12,345 contributions in 2030
        </h2>
        """

        with mock.patch.object(MODULE, "fetch_contributions_html", return_value=html):
            _, yearly_total = MODULE.scrape_contributions(2030)

        self.assertEqual(yearly_total, 12345)

    def test_fetch_all_contributions_sums_full_year_totals_instead_of_truncating(self):
        def fake_scrape(year):
            totals = {
                2024: ({"2024-12-31": 29}, 29),
                2025: ({"2025-12-31": 206}, 206),
                2026: ({"2026-04-13": 1012}, 1012),
            }
            return totals[year]

        class FakeDateTime:
            @staticmethod
            def now(_tz):
                return REAL_DATETIME(2026, 4, 13, tzinfo=MODULE.timezone.utc)

            @staticmethod
            def strptime(value, fmt):
                return REAL_DATETIME.strptime(value, fmt)

        with mock.patch.object(MODULE, "scrape_contributions", side_effect=fake_scrape):
            with mock.patch.object(MODULE, "datetime", FakeDateTime):
                days, total = MODULE.fetch_all_contributions()

        self.assertEqual(total, 1247)
        self.assertEqual(days[-1], ("2026-04-13", 1012))


if __name__ == "__main__":
    unittest.main()
