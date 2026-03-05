#!/usr/bin/env python3
"""Generate an SVG contribution graph using GitHub's GraphQL API."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

USERNAME = "kgarg2468"
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


def main():
    print("Fetching contribution data...")
    days = fetch_contributions()
    print(f"Got {len(days)} days of data")

    svg = generate_svg(days)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "..", "assets", "contribution-graph.svg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        f.write(svg)

    print(f"Written to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
