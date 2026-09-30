#!/usr/bin/env python3
"""Compute lifetime AI token spend from local Claude Code and Codex logs.

Keeps a ledger in ~/Library/Application Support/token-spend/ledger.json that
only ever grows, and publishes aggregate totals (no log content) to
data/tokens.json. `--install` registers a launchd job that uploads every 6h;
`--uninstall` removes it. `--write PATH` writes the JSON locally instead.
The job runs a copy of this file, so rerun `--install` after editing it.
"""

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = "krishhgg/krishhgg"
BRANCH = "main"
REMOTE_PATH = "data/tokens.json"
ENDPOINT = f"repos/{REPO}/contents/{REMOTE_PATH}"
LABEL = "com.krishhgg.token-spend"
GH_FALLBACKS = ["/opt/homebrew/bin/gh", "/usr/local/bin/gh"]
SYSTEM_PYTHON = "/usr/bin/python3"
LEDGER_VERSION = 1
CODEX_FIELDS = ("total_tokens", "cached_input_tokens")


def support_dir(home):
    return os.path.join(home, "Library", "Application Support", "token-spend")


def read_json_lines(path, needle):
    """Yield parsed objects from the lines of path that contain needle."""
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if needle not in line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def scan_claude(home):
    """Per UTC day {all, fresh} from Claude Code transcripts, deduped on (message id, requestId)."""
    days = {}
    seen = set()
    pattern = os.path.join(home, ".claude", "projects", "**", "*.jsonl")
    for path in sorted(glob.glob(pattern, recursive=True)):
        for o in read_json_lines(path, '"usage"'):
            m = o.get("message")
            u = m.get("usage") if isinstance(m, dict) else None
            if not u:
                continue
            key = (m.get("id"), o.get("requestId"))
            if key in seen:
                continue
            seen.add(key)
            ts = o.get("timestamp")
            if not ts:
                continue
            cache_read = u.get("cache_read_input_tokens") or 0
            total = (
                (u.get("input_tokens") or 0)
                + (u.get("output_tokens") or 0)
                + (u.get("cache_creation_input_tokens") or 0)
                + cache_read
            )
            day = days.setdefault(ts[:10], {"all": 0, "fresh": 0})
            day["all"] += total
            day["fresh"] += total - cache_read
    return days


def codex_day(rel_path):
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})/", rel_path)
    if m:
        return "-".join(m.groups())
    m = re.search(r"rollout-(\d{4}-\d{2}-\d{2})", os.path.basename(rel_path))
    return m.group(1) if m else None


def scan_codex_file(path):
    """(all, fresh) this file adds beyond the cumulative total it started from, or None."""
    first = last = None
    for o in read_json_lines(path, "total_token_usage"):
        info = (o.get("payload") or {}).get("info") or {}
        t = info.get("total_token_usage")
        last_usage = info.get("last_token_usage") or {}
        if not t:
            continue
        if first is None:
            first = {k: (t.get(k) or 0) - (last_usage.get(k) or 0) for k in CODEX_FIELDS}
        last = t
    if last is None:
        return None
    delta = {k: (last.get(k) or 0) - first[k] for k in CODEX_FIELDS}
    return delta["total_tokens"], delta["total_tokens"] - delta["cached_input_tokens"]


def scan_codex(home):
    """Per session file {all, fresh, day}, keyed by file name.

    The name carries a UUID and survives the move from sessions/ to
    archived_sessions/, so an archived session keeps its single ledger entry.
    """
    root = os.path.join(home, ".codex")
    files = {}
    for sub in ("sessions", "archived_sessions"):
        pattern = os.path.join(root, sub, "**", "*.jsonl")
        for path in sorted(glob.glob(pattern, recursive=True)):
            counts = scan_codex_file(path)
            if counts is None:
                continue
            rel = os.path.relpath(path, root)
            files[os.path.basename(rel)] = {"all": counts[0], "fresh": counts[1], "day": codex_day(rel)}
    return files


def scan_stats_cache(home):
    """Lump totals from ~/.claude/stats-cache.json, or None if it is missing."""
    path = os.path.join(home, ".claude", "stats-cache.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    total = cache_read = 0
    for counters in (data.get("modelUsage") or {}).values():
        for key, value in counters.items():
            # maxOutputTokens is a limit, not usage
            if key.endswith("Tokens") and not key.startswith("max") and isinstance(value, (int, float)) and not isinstance(value, bool):
                total += int(value)
                if key == "cacheReadInputTokens":
                    cache_read += int(value)
    return {
        "through": (data.get("lastComputedDate") or "")[:10],
        "since": (data.get("firstSessionDate") or "")[:10],
        "all": total,
        "fresh": total - cache_read,
    }


def load_ledger(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"version": LEDGER_VERSION, "stats_cache": None, "codex": {}, "claude": {}}


def merge_counts(stored, fresh):
    """Per-field max so a source that shrank (deleted transcripts) never lowers the ledger."""
    for key, counts in fresh.items():
        current = stored.setdefault(key, {})
        for field, value in counts.items():
            if isinstance(value, (int, float)):
                current[field] = max(current.get(field, value), value)
            elif field not in current:
                current[field] = value


def update_ledger(ledger, claude, codex, stats_cache):
    # The stats cache is a frozen baseline: record it once and never touch it again.
    if ledger.get("stats_cache") is None and stats_cache is not None:
        ledger["stats_cache"] = stats_cache
    merge_counts(ledger.setdefault("claude", {}), claude)
    merge_counts(ledger.setdefault("codex", {}), codex)
    return ledger


def save_ledger(ledger, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="ledger.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def seed_from(published):
    """Frozen baseline from the published totals, or None if they are unusable."""
    total, fresh, updated = published.get("total"), published.get("fresh"), published.get("updated")
    if not (isinstance(total, int) and isinstance(fresh, int) and isinstance(updated, str) and len(updated) >= 10):
        return None
    return {"through": updated[:10], "since": published.get("since"), "all": total, "fresh": fresh}


def summarize(ledger):
    """Return (per-source {all, fresh}, overall {all, fresh}, earliest day)."""
    seed = ledger.get("published")
    # A published seed already covers every source up to its day, the stats cache included
    base = seed or ledger.get("stats_cache") or {}
    through = base.get("through") or ""
    sources = {
        "published" if seed else "stats_cache": {"all": base.get("all", 0), "fresh": base.get("fresh", 0)},
        "claude": {"all": 0, "fresh": 0},
        "codex": {"all": 0, "fresh": 0},
    }
    days = [base["since"]] if base.get("since") else []
    for day, counts in ledger.get("claude", {}).items():
        days.append(day)
        if day <= through:
            continue
        sources["claude"]["all"] += counts["all"]
        sources["claude"]["fresh"] += counts["fresh"]
    for counts in ledger.get("codex", {}).values():
        if counts.get("day"):
            days.append(counts["day"])
        if seed and (counts.get("day") or "") <= through:
            continue
        sources["codex"]["all"] += counts["all"]
        sources["codex"]["fresh"] += counts["fresh"]
    totals = {
        "all": sum(s["all"] for s in sources.values()),
        "fresh": sum(s["fresh"] for s in sources.values()),
    }
    return sources, totals, min(days) if days else None


def compute(home, ledger_path, published=None):
    ledger = load_ledger(ledger_path)
    update_ledger(ledger, scan_claude(home), scan_codex(home), scan_stats_cache(home))
    result = summarize(ledger)
    # Counting less than what is published means the ledger was lost and rebuilt from
    # fewer logs. Start from the published total so uploads resume with the next day's usage.
    seed = seed_from(published) if published and not ledger.get("published") else None
    if seed and seed["all"] > result[1]["all"]:
        ledger["published"] = seed
        result = summarize(ledger)
    save_ledger(ledger, ledger_path)
    return result


def build_output(totals, since, now=None):
    now = now or datetime.now(timezone.utc)
    return {
        "total": int(totals["all"]),
        "fresh": int(totals["fresh"]),
        "since": since,
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def render(output):
    return json.dumps(output, indent=2) + "\n"


def write_output(output, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(output))


def summary_line(sources, totals, since):
    parts = [f"{name} {c['all']}/{c['fresh']}" for name, c in sources.items()]
    parts.append(f"total {totals['all']}/{totals['fresh']} since {since}")
    return "  ".join(parts)


def find_gh():
    gh = shutil.which("gh")
    if gh:
        return gh
    for candidate in GH_FALLBACKS:
        if os.path.exists(candidate):
            return candidate
    raise SystemExit("gh CLI not found")


def gh_api(gh, args, body=None):
    cmd = [gh, "api"] + args
    if body is not None:
        cmd += ["--input", "-"]
    return subprocess.run(cmd, input=body, capture_output=True, text=True)


def fetch_published(gh):
    """(blob sha, parsed JSON) of the published file, or None if it is not on the branch yet."""
    got = gh_api(gh, [f"{ENDPOINT}?ref={BRANCH}"])
    if got.returncode != 0:
        if "404" in got.stderr:
            return None
        raise SystemExit(f"gh api GET failed: {got.stderr.strip()}")
    remote = json.loads(got.stdout)
    try:
        current = json.loads(base64.b64decode(remote.get("content") or "").decode())
    except ValueError:
        current = {}
    return remote["sha"], current


def upload(gh, published, output):
    if published is None:
        print(f"{REMOTE_PATH} is not on {BRANCH} yet; skipping upload")
        return
    sha, current = published
    # Never make the card go down
    if output["total"] <= current.get("total", 0):
        print(f"remote total {current.get('total')} is not below {output['total']}; skipping upload")
        return
    body = json.dumps({
        "message": "Update token spend",
        "content": base64.b64encode(render(output).encode()).decode(),
        "sha": sha,
        "branch": BRANCH,
    })
    put = gh_api(gh, ["-X", "PUT", ENDPOINT], body=body)
    if put.returncode != 0:
        raise SystemExit(f"gh api PUT failed: {put.stderr.strip()}")
    print(f"uploaded {REMOTE_PATH} to {BRANCH}")


def plist_path(home):
    return os.path.join(home, "Library", "LaunchAgents", f"{LABEL}.plist")


def install(home):
    import plistlib  # only needed here; the homebrew python3 on this Mac fails to import it

    dest_dir = support_dir(home)
    os.makedirs(dest_dir, exist_ok=True)
    script = os.path.join(dest_dir, "token_spend.py")
    if os.path.abspath(__file__) != os.path.abspath(script):
        shutil.copyfile(os.path.abspath(__file__), script)
    log = os.path.join(home, "Library", "Logs", "token-spend.log")
    plist = plist_path(home)
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    with open(plist, "wb") as fh:
        plistlib.dump({
            "Label": LABEL,
            # /usr/bin/python3 survives Homebrew and Xcode upgrades
            "ProgramArguments": [SYSTEM_PYTHON if os.path.exists(SYSTEM_PYTHON) else os.path.abspath(sys.executable), script, "--upload"],
            "StartInterval": 21600,
            "RunAtLoad": True,
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
        }, fh)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist], check=True)
    print(f"installed {plist}")


def uninstall(home):
    plist = plist_path(home)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if os.path.exists(plist):
        os.remove(plist)
    print(f"removed {plist}")


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--write", metavar="PATH", help="write tokens.json to PATH")
    parser.add_argument("--upload", action="store_true", help="publish tokens.json to GitHub via gh")
    parser.add_argument("--install", action="store_true", help="install the 6-hourly launchd job")
    parser.add_argument("--uninstall", action="store_true", help="remove the launchd job")
    parser.add_argument("--ledger", metavar="PATH", help="ledger file (default: Application Support)")
    parser.add_argument("--home", metavar="PATH", help="home directory to scan (default: ~)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    home = os.path.abspath(os.path.expanduser(args.home)) if args.home else os.path.expanduser("~")
    if args.install:
        return install(home)
    if args.uninstall:
        return uninstall(home)
    ledger_path = args.ledger or os.path.join(support_dir(home), "ledger.json")
    gh = published = None
    if args.upload:
        gh = find_gh()
        published = fetch_published(gh)
    sources, totals, since = compute(home, ledger_path, published and published[1])
    print(summary_line(sources, totals, since))
    output = build_output(totals, since)
    if args.write:
        write_output(output, args.write)
    if args.upload:
        upload(gh, published, output)


if __name__ == "__main__":
    main()
