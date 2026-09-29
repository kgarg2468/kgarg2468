import base64
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "token_spend.py"
SPEC = importlib.util.spec_from_file_location("token_spend", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def claude_row(msg_id, request_id, timestamp, inp, out, create, read):
    return {
        "timestamp": timestamp,
        "requestId": request_id,
        "message": {
            "id": msg_id,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": create,
                "cache_read_input_tokens": read,
            },
        },
    }


def codex_row(total, cached, last_total, last_cached):
    return {
        "payload": {
            "info": {
                "total_token_usage": {"total_tokens": total, "cached_input_tokens": cached},
                "last_token_usage": {"total_tokens": last_total, "cached_input_tokens": last_cached},
            }
        }
    }


class TokenSpendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.ledger = Path(self.tmp.name) / "ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *extra):
        out = io.StringIO()
        with redirect_stdout(out):
            MODULE.main(["--home", str(self.home), "--ledger", str(self.ledger), *extra])
        return out.getvalue()

    def test_codex_resume_subtracts_parent_baseline(self):
        # First record is cumulative 1000 with 100 from this turn, so the parent left 900 (360 cached).
        write_jsonl(
            self.home / ".codex" / "sessions" / "2026" / "01" / "05" / "rollout-2026-01-05T01-00-00-a.jsonl",
            [codex_row(1000, 400, 100, 40), codex_row(1500, 600, 500, 200)],
        )
        write_jsonl(
            self.home / ".codex" / "archived_sessions" / "rollout-2025-12-26T01-00-00-b.jsonl",
            [codex_row(50, 10, 50, 10)],
        )

        codex = MODULE.scan_codex(str(self.home))

        first = codex["rollout-2026-01-05T01-00-00-a.jsonl"]
        self.assertEqual(first, {"all": 600, "fresh": 360, "day": "2026-01-05"})
        archived = codex["rollout-2025-12-26T01-00-00-b.jsonl"]
        self.assertEqual(archived, {"all": 50, "fresh": 40, "day": "2025-12-26"})

    def test_archiving_a_codex_session_keeps_one_ledger_entry(self):
        live = self.home / ".codex" / "sessions" / "2026" / "02" / "01" / "rollout-2026-02-01T00-00-00-c.jsonl"
        write_jsonl(live, [codex_row(100, 20, 100, 20)])

        before = self.run_main()
        archived = self.home / ".codex" / "archived_sessions" / live.name
        archived.parent.mkdir(parents=True)
        os.rename(live, archived)
        after = self.run_main()

        self.assertIn("codex 100/80", before)
        self.assertEqual(before, after)
        self.assertEqual(list(json.loads(self.ledger.read_text())["codex"]), [live.name])

    def test_claude_dedupes_across_files(self):
        shared = claude_row("msg_1", "req_1", "2026-08-02T10:00:00.000Z", 10, 20, 30, 40)
        write_jsonl(self.home / ".claude" / "projects" / "p1" / "a.jsonl", [shared])
        write_jsonl(
            self.home / ".claude" / "projects" / "p2" / "b.jsonl",
            [shared, claude_row("msg_2", "req_2", "2026-08-03T10:00:00.000Z", 1, 2, 3, 4)],
        )

        claude = MODULE.scan_claude(str(self.home))

        self.assertEqual(claude, {
            "2026-08-02": {"all": 100, "fresh": 60},
            "2026-08-03": {"all": 10, "fresh": 6},
        })

    def test_stats_cache_is_frozen_and_excludes_covered_days(self):
        stats = self.home / ".claude" / "stats-cache.json"
        stats.parent.mkdir(parents=True)
        stats.write_text(json.dumps({
            "firstSessionDate": "2026-01-31T23:50:12.135Z",
            "lastComputedDate": "2026-07-20",
            "modelUsage": {
                "m1": {"inputTokens": 100, "outputTokens": 50, "cacheReadInputTokens": 1000,
                       "cacheCreationInputTokens": 200, "costUSD": 5, "contextWindow": 200000},
            },
        }))
        write_jsonl(self.home / ".claude" / "projects" / "p" / "s.jsonl", [
            claude_row("m_old", "r_old", "2026-07-20T09:00:00.000Z", 1, 1, 1, 1),
            claude_row("m_new", "r_new", "2026-07-21T09:00:00.000Z", 5, 5, 5, 5),
        ])

        first_run = self.run_main()
        stats.write_text(json.dumps({"lastComputedDate": "2026-09-01", "modelUsage": {
            "m1": {"inputTokens": 999999, "cacheReadInputTokens": 0}}}))
        second_run = self.run_main()

        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(ledger["stats_cache"],
                         {"through": "2026-07-20", "since": "2026-01-31", "all": 1350, "fresh": 350})
        self.assertEqual(first_run, second_run)
        self.assertIn("stats_cache 1350/350", first_run)
        self.assertIn("claude 20/15", first_run)
        self.assertIn("total 1370/365 since 2026-01-31", first_run)

    def test_ledger_never_goes_down_when_transcripts_disappear(self):
        transcript = self.home / ".claude" / "projects" / "p" / "old.jsonl"
        write_jsonl(transcript, [claude_row("m1", "r1", "2026-08-01T00:00:00.000Z", 100, 100, 100, 100)])
        write_jsonl(self.home / ".claude" / "projects" / "p" / "new.jsonl",
                    [claude_row("m2", "r2", "2026-09-01T00:00:00.000Z", 1, 1, 1, 1)])

        before = self.run_main()
        os.remove(transcript)
        after = self.run_main()

        self.assertIn("claude 404/303", before)
        self.assertEqual(before, after)
        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(ledger["claude"]["2026-08-01"], {"all": 400, "fresh": 300})

    def test_output_json_shape(self):
        write_jsonl(self.home / ".codex" / "sessions" / "2025" / "12" / "26" / "rollout-x.jsonl",
                    [codex_row(30, 10, 30, 10)])
        write_jsonl(self.home / ".claude" / "projects" / "p" / "s.jsonl",
                    [claude_row("m", "r", "2026-08-01T00:00:00.000Z", 1, 2, 3, 4)])
        out_path = Path(self.tmp.name) / "out" / "tokens.json"

        self.run_main("--write", str(out_path))

        text = out_path.read_text()
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(text, json.dumps(json.loads(text), indent=2) + "\n")
        data = json.loads(text)
        self.assertEqual(list(data), ["total", "fresh", "since", "updated"])
        self.assertEqual(data["total"], 40)
        self.assertEqual(data["fresh"], 26)
        self.assertEqual(data["since"], "2025-12-26")
        self.assertRegex(data["updated"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_default_ledger_lives_under_home(self):
        out = io.StringIO()
        with redirect_stdout(out):
            MODULE.main(["--home", str(self.home)])

        expected = self.home / "Library" / "Application Support" / "token-spend" / "ledger.json"
        self.assertTrue(expected.exists())
        self.assertIn("total 0/0 since None", out.getvalue())


class UploadTests(unittest.TestCase):
    def run_upload(self, remote_total, local_total):
        remote = {"total": remote_total, "fresh": 1, "since": "2025-12-26", "updated": "x"}
        got = SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "sha": "abc", "content": base64.b64encode(json.dumps(remote).encode()).decode()}))
        put = SimpleNamespace(returncode=0, stderr="", stdout="{}")
        calls = []

        def fake_gh_api(gh, args, body=None):
            calls.append(args)
            return got if len(calls) == 1 else put

        local = {"total": local_total, "fresh": 1, "since": "2025-12-26", "updated": "y"}
        out = io.StringIO()
        with mock.patch.object(MODULE, "find_gh", return_value="gh"), \
                mock.patch.object(MODULE, "gh_api", side_effect=fake_gh_api), redirect_stdout(out):
            MODULE.upload(local)
        return calls, out.getvalue()

    def test_skips_a_total_that_would_lower_the_published_one(self):
        for local_total in (99, 100):
            calls, out = self.run_upload(remote_total=100, local_total=local_total)
            self.assertEqual(len(calls), 1, local_total)
            self.assertIn("skipping upload", out)

    def test_uploads_a_higher_total(self):
        calls, out = self.run_upload(remote_total=100, local_total=101)
        self.assertEqual(calls[1][:2], ["-X", "PUT"])
        self.assertIn("uploaded data/tokens.json to main", out)


if __name__ == "__main__":
    unittest.main()
