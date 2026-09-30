import contextlib
import importlib.util
import io
import json
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_readme.py"
SPEC = importlib.util.spec_from_file_location("generate_readme", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SVG_NS = "http://www.w3.org/2000/svg"


class FixtureRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svg = MODULE.render(MODULE.fixture_data())

    def test_parses_as_xml_with_width_850(self):
        root = ET.fromstring(self.svg)
        self.assertEqual(root.tag, f"{{{SVG_NS}}}svg")
        self.assertEqual(root.get("width"), "850")
        self.assertEqual(root.get("viewBox").split()[2], "850")

    def test_no_external_references(self):
        # The only "http" allowed is the SVG namespace itself.
        self.assertEqual(self.svg.count("http"), 1)
        self.assertIn(f'xmlns="{SVG_NS}"', self.svg)
        self.assertNotIn("<image", self.svg)
        self.assertNotIn("href", self.svg)
        self.assertNotIn("<script", self.svg)
        self.assertNotIn("@import", self.svg)

    def test_sections_and_values_present(self):
        for text in (
            "STACK", "28 tools", "CONTRIBUTIONS", "1,738 in the last 31 days", "TOTALS",
            "LANGUAGES", "OPEN SOURCE", "7 public repos with 50+ stars",
            "ESTIMATED TOKEN SPEND", "since dec 2025 · synced sep 29", "≈ 75.85 billion tokens",
            "75.8B/100B", "2/109", "aug 30", "today", "last sync 2026-09-29 20:00 utc",
            "rocketride-org/", "17.3k★", "52.3k★", "13.0k★", "60★",
        ):
            self.assertIn(text, self.svg, text)
        self.assertIn('id="k1-d50-3"', self.svg)
        self.assertIn('id="k1-sh"', self.svg)
        self.assertNotIn("k1-scan", self.svg)
        # Motion on: blinking cursor, dither shimmer, chart reveal.
        self.assertIn('attributeName="patternTransform"', self.svg)
        self.assertIn('attributeName="opacity" values="1;0"', self.svg)
        self.assertIn('<clipPath id="k1-rev">', self.svg)

    def test_oss_rows_capped_at_seven(self):
        data = MODULE.fixture_data()
        data["oss"] = data["oss"] + [["extra/one", 999, 1], ["extra/two", 999, 1]]
        svg = MODULE.render(data)
        self.assertIn("9 public repos with 50+ stars, top 7 below", svg)
        self.assertNotIn("top 7", self.svg)
        self.assertNotIn("extra/", svg)
        self.assertEqual(svg.count('<text x="24" y="190"'), 1)

    def test_total_labels_clear_a_five_digit_number(self):
        def label_x(data):
            root = ET.fromstring(MODULE.render(data))
            xs = [t.get("x") for t in root.iter(f"{{{SVG_NS}}}text") if t.text == "contributions"]
            self.assertEqual(len(xs), 1)
            return float(xs[0])

        data = MODULE.fixture_data()
        self.assertEqual(label_x(data), 623)
        data["total"] = 12345
        # 531 is the column start, 96 is the width of "12,345" at scale 3
        self.assertEqual(label_x(data), 531 + 96 + 14)


class PixelFontTests(unittest.TestCase):
    def test_runs_merges_horizontal_runs(self):
        d = MODULE.runs(["##.##", "#####"], 0, 0, 2)
        self.assertEqual(d, "M0 0h4v2h-4zM6 0h4v2h-4zM0 2h10v2h-10z")

    def test_runs_selects_cell_type(self):
        rows = ["#+.", ".++"]
        self.assertEqual(MODULE.runs(rows, 10, 20, 1, "#"), "M10 20h1v1h-1z")
        self.assertEqual(MODULE.runs(rows, 10, 20, 1, "+"), "M11 20h1v1h-1zM11 21h2v1h-2z")

    def test_px_width(self):
        # A (5) + gap + B (5), minus the trailing gap, times scale.
        self.assertEqual(MODULE.px_width("AB", 1), 11)
        self.assertEqual(MODULE.px_width("AB", 3), 33)
        self.assertEqual(MODULE.px_width("KRISH GARG", 6), 330)
        self.assertEqual(MODULE.px_width("", 6), 0)

    def test_px_text_shadow_is_offset_by_scale(self):
        out = MODULE.px_text("I", 0, 0, 3, "#fff", "url(#k1-sh)")
        self.assertIn('<path fill="url(#k1-sh)" transform="translate(3 3)" d="', out)
        self.assertIn('<path fill="#fff" d="M0 0h9v3h-9zM3 3h3v3h-3z', out)
        self.assertNotIn("translate", MODULE.px_text("I", 0, 0, 3, "#fff"))

    def test_lowercase_and_unknown_glyphs(self):
        self.assertEqual(MODULE.px_path("a", 0, 0, 1), MODULE.px_path("A", 0, 0, 1))
        self.assertEqual(MODULE.px_path("%", 0, 0, 1), MODULE.px_path("?", 0, 0, 1))


class NumberFormattingTests(unittest.TestCase):
    def test_next_milestone(self):
        cases = [(0, 1), (1, 2), (2, 5), (5, 10), (7, 10), (10, 20), (99, 100), (150, 200),
                 (499, 500), (500, 1000), (75846214525, 100000000000)]
        for n, want in cases:
            self.assertEqual(MODULE.next_milestone(n), want, n)

    def test_short_human_stars(self):
        self.assertEqual(MODULE.short(75846214525), "75.8B")
        self.assertEqual(MODULE.short(100000000000), "100B")
        self.assertEqual(MODULE.short(2500000), "2.5M")
        self.assertEqual(MODULE.short(999), "999")
        self.assertEqual(MODULE.human(75846214525), "75.85 billion")
        self.assertEqual(MODULE.human(2501109232), "2.50 billion")
        self.assertEqual(MODULE.human(1234), "1,234")
        self.assertEqual(MODULE.stars(17334), "17.3k★")
        self.assertEqual(MODULE.stars(13025), "13.0k★")
        self.assertEqual(MODULE.stars(60), "60★")

    def test_js_style_number_formatting(self):
        self.assertEqual(MODULE._n(425.0), "425")
        self.assertEqual(MODULE._n(425.5), "425.5")
        self.assertEqual(MODULE.jsround(2.5), 3)
        self.assertEqual(MODULE.jsround(-2.5), -2)
        self.assertEqual(MODULE.to_fixed(45.4, 1), "45.4")
        self.assertEqual(MODULE.to_fixed(0.25, 1), "0.3")

    def test_month_labels(self):
        self.assertEqual(MODULE.month_day("2026-08-30"), "aug 30")
        self.assertEqual(MODULE.month_year("2025-12-26"), "dec 2025")
        # 20:00 UTC is still the 29th in Los Angeles; 06:00 UTC on the 30th is not.
        self.assertEqual(MODULE.month_day("2026-09-29T20:00:00Z", "America/Los_Angeles"), "sep 29")
        self.assertEqual(MODULE.month_day("2026-09-30T06:00:00Z", "America/Los_Angeles"), "sep 29")


def pr_node(repo, owner, stars, private=False):
    return {"repository": {"nameWithOwner": repo, "isPrivate": private, "stargazerCount": stars,
                           "owner": {"login": owner}}}


class PrAggregationTests(unittest.TestCase):
    def test_filters_and_sorts(self):
        nodes = (
            [pr_node("big/one", "big", 500)] * 2
            + [pr_node("small/star", "small", 49)] * 5
            + [pr_node("krishhgg/mine", "krishhgg", 9000)] * 3
            + [pr_node("hidden/private", "hidden", 800, private=True)]
            + [pr_node("mid/two", "mid", 1000)] * 2
            + [pr_node("lone/fifty", "lone", 50)]
            + [{}]  # a search node that is not a pull request
        )
        got = MODULE.aggregate_prs(nodes, login="krishhgg", min_stars=50)
        self.assertEqual(got, [["mid/two", 1000, 2], ["big/one", 500, 2], ["lone/fifty", 50, 1]])
        self.assertEqual(sum(r[2] for r in got), 5)

    def test_owner_match_is_case_insensitive(self):
        got = MODULE.aggregate_prs([pr_node("Krishhgg/x", "Krishhgg", 100)])
        self.assertEqual(got, [])


def repo(name, langs, fork=False):
    return {"nameWithOwner": name, "isFork": fork,
            "languages": {"edges": [{"size": size, "node": {"name": lang}} for lang, size in langs]}}


class LanguageAggregationTests(unittest.TestCase):
    def test_sums_bytes_and_takes_top_n(self):
        repos = [
            repo("me/a", [("TypeScript", 600), ("Python", 200)]),
            repo("me/b", [("Python", 100), ("Shell", 50), ("Rust", 40), ("Swift", 5), ("Go", 3), ("C", 2)]),
            repo("me/forked", [("Java", 100000)], fork=True),
            {"nameWithOwner": "me/empty", "isFork": False, "languages": None},
        ]
        got = MODULE.aggregate_langs(repos, top=6)
        names = [n for n, _ in got]
        self.assertEqual(names, ["TypeScript", "Python", "Shell", "Rust", "Swift", "Go"])
        total = 1000
        self.assertAlmostEqual(got[0][1], 60.0)
        self.assertAlmostEqual(got[1][1], 30.0)
        # Percentages are of all bytes, so the shown six sum to less than 100.
        self.assertAlmostEqual(sum(v for _, v in got), (total - 2) / total * 100)

    def test_empty(self):
        self.assertEqual(MODULE.aggregate_langs([]), [])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def http_401():
    return urllib.error.HTTPError(MODULE.GRAPHQL_URL, 401, "Unauthorized", {}, None)


class TokenFallbackTests(unittest.TestCase):
    def test_401_switches_to_fallback_once(self):
        seen = []

        def fake_urlopen(req, timeout=None):
            auth = req.get_header("Authorization")
            seen.append(auth)
            if auth == "bearer expired":
                raise http_401()
            return FakeResponse({"data": {"ok": len(seen)}})

        gql = MODULE.GraphQL("expired", "fallback")
        out = io.StringIO()
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=fake_urlopen), \
                contextlib.redirect_stdout(out):
            first = gql("query", {})
            second = gql("query", {})
        self.assertEqual(first, {"ok": 2})
        self.assertEqual(second, {"ok": 3})
        # expired, then fallback retry, then fallback directly (no second 401 round trip)
        self.assertEqual(seen, ["bearer expired", "bearer fallback", "bearer fallback"])
        lines = [line for line in out.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 1)
        self.assertIn("401", lines[0])
        self.assertNotIn("expired", lines[0])
        self.assertNotIn("fallback", lines[0].replace("GITHUB_FALLBACK_TOKEN", ""))

    def test_401_without_fallback_raises(self):
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=http_401()):
            with self.assertRaises(urllib.error.HTTPError):
                MODULE.GraphQL("expired")("query", {})

    def test_401_on_fallback_raises(self):
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=http_401()) as m, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(urllib.error.HTTPError):
                MODULE.GraphQL("expired", "also-bad")("query", {})
        self.assertEqual(m.call_count, 2)

    def test_graphql_errors_raise(self):
        with mock.patch.object(MODULE.urllib.request, "urlopen",
                               return_value=FakeResponse({"data": None, "errors": [{"message": "nope"}]})):
            with self.assertRaises(RuntimeError):
                MODULE.GraphQL("tok")("query", {})

    def test_non_401_http_error_propagates(self):
        err = urllib.error.HTTPError(MODULE.GRAPHQL_URL, 502, "Bad Gateway", {}, None)
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=err) as m:
            with self.assertRaises(urllib.error.HTTPError):
                MODULE.GraphQL("tok", "fallback")("query", {})
        self.assertEqual(m.call_count, 1)


if __name__ == "__main__":
    unittest.main()
