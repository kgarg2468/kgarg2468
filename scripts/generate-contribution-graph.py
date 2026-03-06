#!/usr/bin/env python3
"""Generate an SVG contribution graph by scraping GitHub's contribution page."""

import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

USERNAME = "kgarg2468"
ACCOUNT_CREATED = "2024-09-09"

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


def scrape_contributions(year):
    """Scrape contribution data for a given year from GitHub's HTML endpoint.

    Returns (day_counts, yearly_total) where day_counts is dict[str, int]
    mapping date strings to contribution counts.
    """
    url = f"https://github.com/users/{USERNAME}/contributions?from={year}-01-01&to={year}-12-31"
    req = urllib.request.Request(url, headers={"User-Agent": "contribution-graph-generator"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode()

    # Extract yearly total from text like "276 contributions in 2026"
    total_match = re.search(r'(\d+)\s+contributions?\s+in\s+\d{4}', html)
    yearly_total = int(total_match.group(1)) if total_match else 0

    # Extract per-day data: <td> with data-date, followed by <tool-tip> with count
    day_counts = {}
    # Match td elements with data-date and their associated tool-tip text
    for match in re.finditer(
        r'data-date="(\d{4}-\d{2}-\d{2})".*?<tool-tip[^>]*>(.*?)</tool-tip>',
        html,
        re.DOTALL,
    ):
        date_str = match.group(1)
        tooltip = match.group(2).strip()
        count_match = re.search(r'(\d+)\s+contributions?\s+on', tooltip)
        if count_match:
            day_counts[date_str] = int(count_match.group(1))
        else:
            day_counts[date_str] = 0

    return day_counts, yearly_total


def fetch_contributions():
    """Fetch contributions for the last 30 days by scraping GitHub."""
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=30)
    current_year = now.year

    # Scrape current year (and previous year if the 30-day window crosses a year boundary)
    years_needed = {current_year}
    if from_date.year != current_year:
        years_needed.add(from_date.year)

    all_days = {}
    for year in years_needed:
        day_counts, _ = scrape_contributions(year)
        all_days.update(day_counts)

    # Filter to last 30 days
    from_str = from_date.strftime("%Y-%m-%d")
    to_str = now.strftime("%Y-%m-%d")
    days = [
        (date, count)
        for date, count in sorted(all_days.items())
        if from_str <= date <= to_str
    ]
    return days


def fetch_all_contributions():
    """Fetch contributions from account creation to now by scraping GitHub."""
    now = datetime.now(timezone.utc)
    start_year = datetime.strptime(ACCOUNT_CREATED, "%Y-%m-%d").year
    current_year = now.year

    all_days = {}
    total_contributions = 0
    for year in range(start_year, current_year + 1):
        day_counts, yearly_total = scrape_contributions(year)
        all_days.update(day_counts)
        total_contributions += yearly_total

    today_str = now.strftime("%Y-%m-%d")
    filtered = [(d, c) for d, c in sorted(all_days.items()) if d <= today_str]
    return filtered, total_contributions


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


def compute_streak_stats(days, total):
    """Compute current streak and longest streak. Total is provided from scraping."""
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
    """Generate a crystal shard streak stats SVG card."""
    w, h = 490, 165
    font = 'font-family="Segoe UI, Ubuntu, sans-serif"'
    # Diamond geometry
    cy = 68  # diamond center y
    half_h = 45  # diamond half-height
    half_w = 38  # diamond half-width
    col_w = w / 3
    cols = [col_w * 0.5, col_w * 1.5, col_w * 2.5]

    # Flame icon path (12x16, origin at top-center)
    flame = (
        "M0,8 C0,3.5 3,-1 6,-6 C9,-1 12,3.5 12,8 "
        "C12,12 9.5,14 6,14 C2.5,14 0,12 0,8 Z"
    )
    # 4-point star/sparkle path (12x12, origin at center)
    star = (
        "M0,-6 C1,-2 2,-1 6,0 C2,1 1,2 0,6 "
        "C-1,2 -2,1 -6,0 C-2,-1 -1,-2 0,-6 Z"
    )

    defs = """<defs>
    <linearGradient id="diamond-fill" x1="0%" y1="0%" x2="100%" y2="100%" gradientTransform="rotate(135)">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="diamond-stroke" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#58a6ff" stop-opacity="0.6"/>
      <stop offset="50%" stop-color="#f59e0b" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.6"/>
    </linearGradient>
    <linearGradient id="diamond-stroke-amber" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.5"/>
      <stop offset="50%" stop-color="#f97316" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.5"/>
    </linearGradient>
    <linearGradient id="fire-grad" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#f97316"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>"""

    # Refraction lines (subtle diagonal lines across background)
    refraction = (
        f'<line x1="60" y1="0" x2="180" y2="{h}" stroke="#58a6ff" stroke-opacity="0.06" stroke-width="0.5"/>'
        f'<line x1="200" y1="0" x2="320" y2="{h}" stroke="#58a6ff" stroke-opacity="0.05" stroke-width="0.5"/>'
        f'<line x1="340" y1="0" x2="460" y2="{h}" stroke="#58a6ff" stroke-opacity="0.06" stroke-width="0.5"/>'
        f'<line x1="430" y1="0" x2="550" y2="{h}" stroke="#58a6ff" stroke-opacity="0.04" stroke-width="0.5"/>'
    )

    def diamond(cx, stroke_grad="diamond-stroke"):
        top = f"{cx},{cy - half_h}"
        right = f"{cx + half_w},{cy}"
        bottom = f"{cx},{cy + half_h}"
        left = f"{cx - half_w},{cy}"
        path = f"M{top} L{right} L{bottom} L{left} Z"
        facet = f'<line x1="{cx - half_w + 6}" y1="{cy}" x2="{cx + half_w - 6}" y2="{cy}" stroke="#58a6ff" stroke-opacity="0.08" stroke-width="0.5"/>'
        return (
            f'<path d="{path}" fill="url(#diamond-fill)" stroke="url(#{stroke_grad})" stroke-width="1.5"/>'
            f'{facet}'
        )

    def fire_icon(cx):
        tx = cx - 6
        ty = cy - half_h - 12
        return f'<path d="{flame}" fill="url(#fire-grad)" transform="translate({tx},{ty})"/>'

    def star_icon(cx):
        return f'<path d="{star}" fill="#58a6ff" fill-opacity="0.8" transform="translate({cx},{cy - half_h - 2})"/>'

    def stat_text(cx, value, suffix="", label="", subtitle=""):
        parts = []
        # Value text with glow
        parts.append(
            f'<text x="{cx}" y="{cy + 5}" fill="#58a6ff" font-size="26" font-weight="700" '
            f'text-anchor="middle" {font} filter="url(#glow)">{value}</text>'
        )
        # Suffix (e.g. "days")
        if suffix:
            parts.append(
                f'<text x="{cx}" y="{cy + 18}" fill="#8b949e" font-size="11" '
                f'text-anchor="middle" {font}>{suffix}</text>'
            )
        # Label below diamond
        if label:
            parts.append(
                f'<text x="{cx}" y="{cy + half_h + 16}" fill="#c9d1d9" font-size="13" '
                f'font-weight="600" text-anchor="middle" {font}>{label}</text>'
            )
        # Subtitle
        if subtitle:
            parts.append(
                f'<text x="{cx}" y="{cy + half_h + 30}" fill="#8b949e" font-size="9" '
                f'text-anchor="middle" {font}>{subtitle}</text>'
            )
        return "\n    ".join(parts)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  {defs}
  <rect width="{w}" height="{h}" fill="#0d1117" rx="6"/>
  {refraction}
  {diamond(cols[0])}
  {star_icon(cols[0])}
  {stat_text(cols[0], f"{total:,}", label="Total Contributions")}
  {diamond(cols[1], "diamond-stroke-amber")}
  {fire_icon(cols[1])}
  {stat_text(cols[1], current_streak, suffix="days", label="Current Streak")}
  {diamond(cols[2], "diamond-stroke-amber")}
  {fire_icon(cols[2])}
  {stat_text(cols[2], longest_streak, suffix="days", label="Longest Streak")}
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
    all_days, total_contributions = fetch_all_contributions()
    print(f"Got {len(all_days)} total days of data")

    total, current_streak, longest_streak = compute_streak_stats(all_days, total_contributions)
    print(f"Total: {total}, Current streak: {current_streak}, Longest: {longest_streak}")

    streak_svg = generate_streak_svg(total, current_streak, longest_streak)
    streak_path = os.path.join(assets_dir, "streak-stats.svg")
    with open(streak_path, "w") as f:
        f.write(streak_svg)
    print(f"Written to {os.path.abspath(streak_path)}")


if __name__ == "__main__":
    main()
