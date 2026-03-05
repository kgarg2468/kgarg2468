#!/usr/bin/env python3
"""Generate an SVG contribution graph using GitHub's GraphQL API."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

USERNAME = "kgarg2468"
ACCOUNT_CREATED = "2024-09-09"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")

GRAPHQL_QUERY = """
query($username: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $username) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

# Chart styling
BG_COLOR = "#0d1117"
LINE_COLOR = "#58a6ff"
POINT_COLOR = "#ffffff"
TEXT_COLOR = "#8b949e"
GRID_COLOR = "#21262d"
AREA_COLOR = "rgba(88, 166, 255, 0.15)"

WIDTH = 850
HEIGHT = 300
PADDING_LEFT = 55
PADDING_RIGHT = 25
PADDING_TOP = 45
PADDING_BOTTOM = 40


def fetch_contributions():
    now = datetime.now(timezone.utc)
    to_date = now.replace(hour=23, minute=59, second=59)
    from_date = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0)

    variables = {
        "username": USERNAME,
        "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    payload = json.dumps({"query": GRAPHQL_QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "contribution-graph-generator",
        },
    )

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    days = []
    for week in data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            days.append((day["date"], day["contributionCount"]))

    days.sort(key=lambda d: d[0])
    return days


def generate_svg(days):
    n = len(days)
    if n == 0:
        return "<svg></svg>"

    counts = [c for _, c in days]
    max_count = max(max(counts), 1)

    chart_w = WIDTH - PADDING_LEFT - PADDING_RIGHT
    chart_h = HEIGHT - PADDING_TOP - PADDING_BOTTOM

    def x(i):
        return PADDING_LEFT + (i / (n - 1)) * chart_w if n > 1 else PADDING_LEFT + chart_w / 2

    def y(val):
        return PADDING_TOP + chart_h - (val / max_count) * chart_h

    # Build grid lines
    grid_lines = []
    num_grid = 5
    for i in range(num_grid + 1):
        val = round(max_count * i / num_grid)
        yy = y(val)
        grid_lines.append(f'<line x1="{PADDING_LEFT}" y1="{yy:.1f}" x2="{WIDTH - PADDING_RIGHT}" y2="{yy:.1f}" stroke="{GRID_COLOR}" stroke-width="1"/>')
        grid_lines.append(f'<text x="{PADDING_LEFT - 10}" y="{yy + 4:.1f}" fill="{TEXT_COLOR}" font-size="11" text-anchor="end" font-family="Segoe UI, Ubuntu, sans-serif">{val}</text>')

    # X-axis labels (show every ~5 days)
    x_labels = []
    step = max(1, n // 6)
    for i in range(0, n, step):
        date_str = days[i][0]
        label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d")
        x_labels.append(f'<text x="{x(i):.1f}" y="{HEIGHT - 5}" fill="{TEXT_COLOR}" font-size="11" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>')
    # Always show last day
    if (n - 1) % step != 0:
        label = datetime.strptime(days[-1][0], "%Y-%m-%d").strftime("%b %d")
        x_labels.append(f'<text x="{x(n-1):.1f}" y="{HEIGHT - 5}" fill="{TEXT_COLOR}" font-size="11" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>')

    # Build polyline points
    points = " ".join(f"{x(i):.1f},{y(c):.1f}" for i, c in enumerate(counts))

    # Area polygon (line + bottom edge)
    area_points = f"{x(0):.1f},{y(0):.1f} " + points + f" {x(n-1):.1f},{PADDING_TOP + chart_h:.1f} {x(0):.1f},{PADDING_TOP + chart_h:.1f}"

    # Dot elements
    dots = []
    for i, c in enumerate(counts):
        dots.append(f'<circle cx="{x(i):.1f}" cy="{y(c):.1f}" r="3" fill="{POINT_COLOR}" opacity="0.9"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{BG_COLOR}" rx="6"/>
  <text x="{WIDTH / 2}" y="28" fill="{LINE_COLOR}" font-size="14" font-weight="600" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{USERNAME}'s Contribution Graph</text>
  {"".join(grid_lines)}
  {"".join(x_labels)}
  <polygon points="{area_points}" fill="{AREA_COLOR}"/>
  <polyline points="{points}" fill="none" stroke="{LINE_COLOR}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  {"".join(dots)}
</svg>'''
    return svg


def fetch_all_contributions():
    """Fetch contributions from account creation to now, handling the 1-year API limit."""
    now = datetime.now(timezone.utc)
    start = datetime.strptime(ACCOUNT_CREATED, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Build year-long (max) date ranges
    ranges = []
    cursor = start
    while cursor < now:
        end = min(cursor + timedelta(days=365), now)
        ranges.append((cursor, end))
        cursor = end + timedelta(seconds=1)

    all_days = {}
    for from_date, to_date in ranges:
        variables = {
            "username": USERNAME,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        payload = json.dumps({"query": GRAPHQL_QUERY, "variables": variables}).encode()
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=payload,
            headers={
                "Authorization": f"bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "contribution-graph-generator",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        for week in data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                all_days[day["date"]] = day["contributionCount"]

    # Return sorted list of (date_str, count)
    return sorted(all_days.items(), key=lambda d: d[0])


def compute_streak_stats(days):
    """Compute total contributions, current streak, and longest streak."""
    total = sum(c for _, c in days)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Current streak: consecutive days ending today (or yesterday)
    current_streak = 0
    for date_str, count in reversed(days):
        if current_streak == 0 and count == 0:
            # Allow today to have 0 (day not over yet), check from yesterday
            if date_str == today:
                continue
            else:
                break
        if count > 0:
            current_streak += 1
        else:
            break

    # Longest streak
    longest_streak = 0
    run = 0
    for _, count in days:
        if count > 0:
            run += 1
            longest_streak = max(longest_streak, run)
        else:
            run = 0

    return total, current_streak, longest_streak


def generate_streak_svg(total, current_streak, longest_streak):
    """Generate a streak stats SVG card matching the dark theme."""
    w, h = 490, 165
    accent = "#58a6ff"
    text_color = "#c9d1d9"
    sub_color = "#8b949e"
    bg = "#0d1117"
    separator = "#21262d"

    date_range = f"{ACCOUNT_CREATED} - Present"

    # Three columns, evenly spaced
    col_w = w / 3
    cols = [col_w * 0.5, col_w * 1.5, col_w * 2.5]

    def column(cx, label, value, subtitle=""):
        sub_el = f'<text x="{cx}" y="118" fill="{sub_color}" font-size="11" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{subtitle}</text>' if subtitle else ""
        return f"""<text x="{cx}" y="62" fill="{accent}" font-size="28" font-weight="700" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{value}</text>
    <text x="{cx}" y="88" fill="{text_color}" font-size="13" font-weight="500" text-anchor="middle" font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>
    {sub_el}"""

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="{bg}" rx="6"/>
  <line x1="{col_w}" y1="30" x2="{col_w}" y2="135" stroke="{separator}" stroke-width="1"/>
  <line x1="{col_w * 2}" y1="30" x2="{col_w * 2}" y2="135" stroke="{separator}" stroke-width="1"/>
  {column(cols[0], "Total Contributions", f"{total:,}", date_range)}
  {column(cols[1], "Current Streak", f"{current_streak} days")}
  {column(cols[2], "Longest Streak", f"{longest_streak} days")}
</svg>'''
    return svg


def main():
    print("Fetching contribution data (last 30 days)...")
    days = fetch_contributions()
    print(f"Got {len(days)} days of data")

    svg = generate_svg(days)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(script_dir, "..", "assets")
    os.makedirs(assets_dir, exist_ok=True)

    graph_path = os.path.join(assets_dir, "contribution-graph.svg")
    with open(graph_path, "w") as f:
        f.write(svg)
    print(f"Written to {os.path.abspath(graph_path)}")

    print("Fetching all contributions for streak stats...")
    all_days = fetch_all_contributions()
    print(f"Got {len(all_days)} total days of data")

    total, current_streak, longest_streak = compute_streak_stats(all_days)
    print(f"Total: {total}, Current streak: {current_streak}, Longest: {longest_streak}")

    streak_svg = generate_streak_svg(total, current_streak, longest_streak)
    streak_path = os.path.join(assets_dir, "streak-stats.svg")
    with open(streak_path, "w") as f:
        f.write(streak_svg)
    print(f"Written to {os.path.abspath(streak_path)}")


if __name__ == "__main__":
    main()
