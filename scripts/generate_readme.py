#!/usr/bin/env python3
"""Generate assets/readme.svg, the single card the profile README shows.

This is a Python port of the "terminal" layout in design/readme-lab.html with
the approved settings baked in: dither bars, brand-color logos on a 24px grid,
motion on, scanlines off, dark framed palette, width 850.

Rendering is pure: render(data) -> str. Network fetching lives in build_data().
Stdlib only, Python 3.12.
"""

import argparse
import importlib.util
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STACK_PATH = ROOT / "data" / "stack.json"
TOKENS_PATH = ROOT / "data" / "tokens.json"
OUT_PATH = ROOT / "assets" / "readme.svg"
GRAPH_SCRIPT = ROOT / "scripts" / "generate-contribution-graph.py"

LOGIN = "kgarg2468"
NAME = "KRISH GARG"
WIDTH = 850
P = 24
MIN_STARS = 50
MAX_OSS_ROWS = 7
LOCAL_TZ = "America/Los_Angeles"
GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "kgarg2468-readme-generator"
MOTION = True
SVG_ID = "k1"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
PALETTE = SimpleNamespace(
    bg="#0a0a0a", border="#262626", ink="#ededed", mid="#a3a3a3", dim="#5f5f5f",
    faint="#2a2a2a", track="#151515", tick="#cdcdcd", shadow="#4d4d4d",
)
BLINK = (
    '<animate attributeName="opacity" values="1;0" keyTimes="0;.5" '
    'calcMode="discrete" dur="1.1s" repeatCount="indefinite"/>'
)

# ---------- 5x7 pixel font ----------
FONT = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###", "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "#####|...#.|..#..|...#.|....#|#...#|.###.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
    ",": "..|..|..|..|.#|.#|#.", ".": ".|.|.|.|.|.|#", " ": "...|...|...|...|...|...|...",
    "-": "....|....|....|####|....|....|....", "/": "....#|....#|...#.|..#..|.#...|#....|#....",
    ":": ".|#|.|.|.|#|.", "!": "#|#|#|#|#|.|#", "'": "#|#|.|.|.|.|.", "_": ".....|.....|.....|.....|.....|.....|#####",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....", "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "&": ".##..|#..#.|.##..|.#...|#.#.#|#..#.|.##.#", "~": ".....|.....|.#...|#.#.#|...#.|.....|.....",
}
GL = {k: v.split("|") for k, v in FONT.items()}


def glyph(ch):
    return GL.get(ch) or GL.get(ch.upper()) or GL["?"]


def px_width(text, s):
    w = 0
    for ch in text:
        w += len(glyph(ch)[0]) + 1
    return max(0, w - 1) * s


def _n(v):
    """Format a number the way a JS template literal would (no trailing .0)."""
    if isinstance(v, int):
        return str(v)
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def num(v):
    return _n(round(v, 2))


def jsround(v):
    """Math.round: halves round toward +infinity."""
    return math.floor(v + 0.5)


def to_fixed(v, digits):
    """Number.prototype.toFixed: round half up on the exact binary value."""
    q = Decimal(1).scaleb(-digits)
    return str(Decimal(v).quantize(q, rounding=ROUND_HALF_UP))


def runs(rows, x, y, s, ch="#"):
    """Rows of cells -> path data, merging horizontal runs of `ch`."""
    d = []
    for r, row in enumerate(rows):
        c = 0
        n = len(row)
        while c < n:
            if row[c] != ch:
                c += 1
                continue
            e = c
            while e < n and row[e] == ch:
                e += 1
            d.append(f"M{num(x + c * s)} {num(y + r * s)}h{num((e - c) * s)}v{num(s)}h{num(-(e - c) * s)}z")
            c = e
    return "".join(d)


def px_path(text, x, y, s):
    d = []
    cx = x
    for ch in text:
        g = glyph(ch)
        d.append(runs(g, cx, y, s))
        cx += (len(g[0]) + 1) * s
    return "".join(d)


def px_text(text, x, y, s, fill, shadow=None):
    d = px_path(text, x, y, s)
    out = ""
    if shadow:
        out += f'<path fill="{shadow}" transform="translate({_n(s)} {_n(s)})" d="{d}"/>'
    return out + f'<path fill="{fill}" d="{d}"/>'


# ---------- helpers ----------
def esc(v):
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fmt(n):
    return f"{jsround(n):,}"


def T(x, y, text, size=12, fill=None, anchor="start", weight=400):
    w = f' font-weight="{weight}"' if weight != 400 else ""
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" font-family="{MONO}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}"{w}>{esc(text)}</text>'
    )


def head(x, label, extra, p):
    tail = f'<tspan fill="{p.dim}" letter-spacing="0">  ·  {esc(extra)}</tspan>' if extra else ""
    return (
        f'<text x="{_n(x)}" y="24" font-family="{MONO}" font-size="12" letter-spacing=".6" '
        f'fill="{p.mid}">{esc(label)}{tail}</text>'
    )


def rect(x, y, w, h, fill, inner=""):
    return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="{fill}">{inner}</rect>' if inner \
        else f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="{fill}"/>'


def short(n):
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            s = to_fixed(n / div, 1)
            return (s[:-2] if s.endswith(".0") else s) + suffix
    return str(n)


def human(n):
    if n >= 1e9:
        return to_fixed(n / 1e9, 2) + " billion"
    if n >= 1e6:
        return to_fixed(n / 1e6, 2) + " million"
    return fmt(n)


def stars(n):
    return (to_fixed(n / 1000, 1) + "k" if n >= 1000 else str(n)) + "★"


def next_milestone(n):
    for e in range(16):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if v > n:
                return v
    return n or 1


def defs(ctx):
    p, uid = ctx.p, ctx.id
    cells = {"d25": [(0, 0)], "d50": [(0, 0), (1, 1)], "d75": [(0, 0), (1, 0), (0, 1)]}
    o = []
    for c in (2, 3):
        for k, cs in cells.items():
            anim = (
                f'<animateTransform attributeName="patternTransform" type="translate" values="0 0;{c} 0" '
                f'dur="1.2s" calcMode="discrete" repeatCount="indefinite"/>'
            ) if MOTION and k == "d50" and c == 3 else ""
            cells_svg = "".join(
                f'<rect x="{x * c}" y="{y * c}" width="{c}" height="{c}" fill="{p.ink}"/>' for x, y in cs
            )
            o.append(
                f'<pattern id="{uid}-{k}-{c}" width="{2 * c}" height="{2 * c}" patternUnits="userSpaceOnUse">'
                f"{cells_svg}{anim}</pattern>"
            )
    o.append(
        f'<pattern id="{uid}-sh" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="2" height="2" fill="{p.shadow}"/><rect x="2" y="2" width="2" height="2" fill="{p.shadow}"/></pattern>'
    )
    return "".join(o)


# ---------- bars ----------
def bar(x, y, w, h, frac, ctx):
    p, uid = ctx.p, ctx.id
    frac = max(0, min(1, frac))
    c = 3
    o = [rect(x, y, w, h, p.track)]
    for i in range(1, 10):
        tx = jsround(x + w * i / 10)
        o.append(rect(tx, y + h - 3, 1, 3, p.faint))
    fw = jsround(frac * w / c) * c
    if fw <= 0:
        return "".join(o)
    solid = max(0, fw - 2 * c)
    o.append(rect(x, y, solid, h, p.ink))
    for i in range(1, 10):
        tx = jsround(x + w * i / 10)
        if tx < x + solid - 1:
            o.append(rect(tx, y, 1, h, p.tick))
    for i, k in enumerate(("d75", "d50", "d25")):
        fx = x + solid + i * c
        if fx >= x + w:
            continue
        o.append(rect(fx, y, min(c, x + w - fx), h, f"url(#{uid}-{k}-3)"))
    return "".join(o)


def chart(x, y, w, h, data, ctx):
    p, uid = ctx.p, ctx.id
    n = len(data)
    col_w = w / n
    bw = max(2, math.floor(col_w) - 3)
    mx = max(data)
    c = 3
    rows = math.floor(h / c)
    o = []
    max_label = ""
    for i, v in enumerate(data):
        bx = jsround(x + i * col_w)
        k = max(1, jsround(v / mx * rows)) if v > 0 else 0
        if not k:
            o.append(rect(bx, y + h - 2, bw, 2, p.faint))
            continue
        top = y + h - k * c
        if k > 1:
            o.append(rect(bx, top + c, bw, (k - 1) * c, p.ink))
        o.append(rect(bx, top, bw, c, f"url(#{uid}-{'d50' if k > 1 else 'd75'}-3)"))
        if v == mx:
            max_label = T(bx + bw / 2, top - 6, fmt(v), size=10, fill=p.mid, anchor="middle")
    steps = 8
    ys, hs = [], []
    for i in range(steps + 1):
        hh = jsround(h * i / steps)
        ys.append(y + h - hh)
        hs.append(hh)
    reveal = (
        f'<animate attributeName="y" values="{";".join(map(_n, ys))}" dur=".8s" calcMode="discrete" fill="freeze"/>'
        f'<animate attributeName="height" values="{";".join(map(_n, hs))}" dur=".8s" calcMode="discrete" fill="freeze"/>'
    ) if MOTION else ""
    return (
        f'<clipPath id="{uid}-rev"><rect x="{_n(x - 2)}" y="{_n(y)}" width="{_n(w + 4)}" height="{_n(h)}">{reveal}</rect></clipPath>'
        f'<line x1="{_n(x)}" x2="{_n(x + w - 3)}" y1="{_n(y + h + 4.5)}" y2="{_n(y + h + 4.5)}" stroke="{p.faint}" stroke-dasharray="3 3"/>'
        f'<g clip-path="url(#{uid}-rev)">{"".join(o)}</g>{max_label}'
    )


# ---------- logos (pre-cut in data/stack.json, one cell = 1px) ----------
def icon(it, x, y, size):
    top = y + (size - it["h"]) / 2
    out = []
    for layer in it["layers"]:
        solid = runs(layer["rows"], x, top, 1, "#")
        soft = runs(layer["rows"], x, top, 1, "+")
        if solid:
            out.append(f'<path fill="#{layer["color"]}" d="{solid}"/>')
        if soft:
            out.append(f'<path fill="#{layer["color"]}" fill-opacity=".45" d="{soft}"/>')
    return "".join(out)


# ---------- sections: each returns (height, svg) ----------
def sec_header(w, ctx, data):
    p, uid = ctx.p, ctx.id
    o = [
        f'<text x="{P}" y="23" font-family="{MONO}" font-size="13" font-weight="700" fill="{p.ink}">{esc(data["login"])}</text>',
        f'<text x="{_n(w - P)}" y="23" font-family="{MONO}" font-size="13" text-anchor="end" fill="{p.dim}">~/<tspan fill="{p.ink}">readme</tspan></text>',
        f'<line x1="0" x2="{_n(w)}" y1="36.5" y2="36.5" stroke="{p.faint}" stroke-dasharray="4 3"/>',
    ]
    name = (data["name"] or " ").upper()
    s = 6
    while s > 3 and px_width(name, s) + 4 * s > w - 2 * P:
        s -= 1
    ny = 60
    o.append(px_text(name, P, ny, s, p.ink, f"url(#{uid}-sh)"))
    o.append(rect(P + px_width(name, s) + 2 * s, ny, 3 * s, 7 * s, p.ink, BLINK if MOTION else ""))
    return ny + 7 * s + 28, "".join(o)


def sec_stack(w, ctx, data):
    p = ctx.p
    stack = data["stack"]
    sz, g, sep = stack["size"], 10, 30
    rows = stack["rows"]
    count = sum(len(grp) for row in rows for grp in row)
    o = [head(P, "STACK", f"{count} tools", p)]
    y = 44
    for row in rows:
        total = 0
        for i, grp in enumerate(row):
            total += sum(it["w"] for it in grp) + (len(grp) - 1) * g + (sep if i else 0)
        x = jsround((w - total) / 2)
        for i, grp in enumerate(row):
            if i:
                o.append(T(x + sep / 2, y + sz / 2 + 4, "·", size=13, fill=p.dim, anchor="middle"))
                x += sep
            for it in grp:
                o.append(icon(it, x, y, sz))
                x += it["w"] + g
            x -= g
        y += sz + 16
    return y + 8, "".join(o)


def sec_activity(w, ctx, data):
    p = ctx.p
    d = data["days"]
    total = sum(d)
    cw, top, h = 15 * len(d), 45, 114
    o = [head(P, "CONTRIBUTIONS", f"{fmt(total)} in the last {len(d)} days", p)]
    o.append(chart(P, top, cw, h, d, ctx))
    o.append(T(P, top + h + 24, data["days_from"], size=11, fill=p.dim))
    o.append(T(P + cw - 3, top + h + 24, "today", size=11, fill=p.dim, anchor="end"))
    rx = P + cw + 42
    rw = w - P - rx
    o.append(head(rx, "TOTALS", "", p))
    streak, best = data["streak"], data["best"]
    lines = [(fmt(data["total"]), "contributions"), (str(streak), "day streak, current"), (str(best), "day streak, best")]
    for i, (n, label) in enumerate(lines):
        y = top + i * 33
        o.append(px_text(n, rx, y, 3, p.ink))
        o.append(T(rx + 92, y + 16, label, size=12, fill=p.mid))
    by = 150
    o.append(bar(rx, by, rw - 64, 15, streak / best if best else 0, ctx))
    o.append(T(w - P, by + 14, f"{streak}/{best}", size=17, fill=p.ink, anchor="end"))
    return 198, "".join(o)


def sec_langs(w, ctx, data):
    p = ctx.p
    o = [head(P, "LANGUAGES", "by bytes", p)]
    for i, (name, v) in enumerate(data["langs"]):
        y = 45 + i * 24
        bx = P + 96
        bw = w - P - bx - 54
        o.append(T(P, y + 10, name.lower(), size=12, fill=p.mid))
        o.append(bar(bx, y, bw, 12, v / 100, ctx))
        o.append(T(w - P, y + 10, to_fixed(v, 1) + "%", size=12, fill=p.ink, anchor="end"))
    return 198, "".join(o)


def sec_oss(w, ctx, data):
    p, uid = ctx.p, ctx.id
    lst = data["oss"]
    total = str(sum(r[2] for r in lst))
    o = [head(P, "OPEN SOURCE", "merged prs", p)]
    o.append(px_text(total, P, 42, 4, p.ink, f"url(#{uid}-sh)"))
    lx = P + px_width(total, 4) + 18
    o.append(T(lx, 55, "merged pull requests", size=12, fill=p.mid))
    o.append(T(lx, 70, f"{len(lst)} public repos with 50+ stars", size=11, fill=p.dim))
    for i, (repo, st, n) in enumerate(lst[:MAX_OSS_ROWS]):
        y = 97 + i * 15.5
        owner, name = repo.split("/", 1)
        o.append(
            f'<text x="{P}" y="{_n(y)}" font-family="{MONO}" font-size="11" fill="{p.dim}">{esc(owner)}/'
            f'<tspan fill="{p.mid}">{esc(name)}</tspan></text>'
        )
        o.append(T(w - P - 34, y, stars(st), size=11, fill=p.dim, anchor="end"))
        o.append(T(w - P, y, str(n), size=11, fill=p.ink, anchor="end"))
    return 198, "".join(o)


def sec_tokens(w, ctx, data):
    p, uid = ctx.p, ctx.id
    tk = data["tokens"]
    t = max(0, jsround(tk["total"] or 0))
    text = fmt(t)
    o = [head(P, "ESTIMATED TOKEN SPEND", f"since {tk['since']} · synced {tk['synced']}", p)]
    s = 5
    limit = w * 0.62 if w > 500 else w - 2 * P
    while s > 2 and px_width(text, s) > limit:
        s -= 1
    ny = 42
    nw = px_width(text, s)
    o.append(px_text(text, P, ny, s, p.ink, f"url(#{uid}-sh)"))
    if w > 500:
        o.append(T(P + nw + 26, ny + 7 * s / 2 + 5, f"≈ {human(t)} tokens", size=13, fill=p.mid))
    else:
        o.append(T(P, ny + 7 * s + 22, f"≈ {human(t)} tokens", size=12, fill=p.mid))
    ms = next_milestone(t)
    by = math.ceil((ny + 7 * s + (18 if w > 500 else 36)) / 3) * 3
    o.append(bar(P, by, w - 2 * P - 116, 15, t / ms, ctx))
    o.append(T(w - P, by + 14, f"{short(t)}/{short(ms)}", size=17, fill=p.ink, anchor="end"))
    return by + 15 + 22, "".join(o)


def sec_footer(w, ctx, data):
    p = ctx.p
    stamp = data["generated_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M utc")
    o = [
        rect(P, 14, 6, 6, p.ink, BLINK if MOTION else ""),
        T(P + 14, 21, "regenerated every 6h by github actions", size=11, fill=p.dim),
        T(w - P, 21, f"last sync {stamp}", size=11, fill=p.dim, anchor="end"),
    ]
    return 34, "".join(o)


def two_col(w, ctx, data, a_fn, b_fn):
    half = w / 2
    ah, a = a_fn(half, ctx, data)
    bh, b = b_fn(half, ctx, data)
    h = max(ah, bh)
    return h, (
        f'{a}<line x1="{_n(half + .5)}" x2="{_n(half + .5)}" y1="0" y2="{_n(h)}" stroke="{ctx.p.faint}" stroke-dasharray="4 3"/>'
        f'<g transform="translate({_n(half)} 0)">{b}</g>'
    )


def wrap_svg(w, h, body, ctx):
    p = ctx.p
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(w)}" height="{_n(h)}" viewBox="0 0 {_n(w)} {_n(h)}">'
        f"<defs>{defs(ctx)}</defs>"
        f'<rect width="{_n(w)}" height="{_n(h)}" fill="{p.bg}"/>{body}'
        f'<rect x=".5" y=".5" width="{_n(w - 1)}" height="{_n(h - 1)}" fill="none" stroke="{p.border}"/></svg>'
    )


def render(data):
    """Pure: data dict -> SVG string (the terminal composition from the lab)."""
    ctx = SimpleNamespace(p=PALETTE, id=SVG_ID)
    w = WIDTH
    secs = [
        sec_header(w, ctx, data),
        sec_stack(w, ctx, data),
        sec_activity(w, ctx, data),
        two_col(w, ctx, data, sec_langs, sec_oss),
        sec_tokens(w, ctx, data),
        sec_footer(w, ctx, data),
    ]
    y = 0
    body = []
    for i, (h, svg) in enumerate(secs):
        if i:
            body.append(f'<line x1="0" x2="{_n(w)}" y1="{_n(y + .5)}" y2="{_n(y + .5)}" stroke="{ctx.p.faint}" stroke-dasharray="4 3"/>')
        body.append(f'<g transform="translate(0 {_n(y)})">{svg}</g>')
        y += h
    return wrap_svg(w, y, "".join(body), ctx)


# ---------- data ----------
def load_stack():
    return json.loads(STACK_PATH.read_text(encoding="utf-8"))


def load_graph_module():
    spec = importlib.util.spec_from_file_location("generate_contribution_graph", GRAPH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def month_day(iso, tz=None):
    """'2026-08-30' -> 'aug 30'. With tz, an ISO timestamp is converted first."""
    d = datetime.fromisoformat(iso)
    if tz:
        d = d.astimezone(ZoneInfo(tz))
    return f"{d:%b} {d.day}".lower()


def month_year(iso):
    d = datetime.fromisoformat(iso)
    return f"{d:%b %Y}".lower()


class GraphQL:
    """POSTs to the GitHub GraphQL API.

    If the primary token is rejected with HTTP 401 and a fallback token is set,
    the request is retried with the fallback, which is then used from that
    point on.
    """

    def __init__(self, token, fallback=None):
        self.token = token
        self.fallback = fallback
        self.switched = False

    def _post(self, query, variables):
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            GRAPHQL_URL, data=body, method="POST",
            headers={
                "Authorization": f"bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def __call__(self, query, variables):
        try:
            payload = self._post(query, variables)
        except urllib.error.HTTPError as err:
            if err.code == 401 and self.fallback and not self.switched:
                print("GITHUB_TOKEN was rejected (401); retrying with GITHUB_FALLBACK_TOKEN")
                self.token = self.fallback
                self.switched = True
                payload = self._post(query, variables)
            else:
                raise
        if payload.get("errors"):
            raise RuntimeError(f"graphql errors: {payload['errors']}")
        return payload["data"]


REPOS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        isFork
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

PRS_QUERY = """
query($q: String!, $after: String) {
  search(type: ISSUE, query: $q, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        repository { nameWithOwner isPrivate stargazerCount owner { login } }
      }
    }
  }
}
"""


def fetch_repos(gql, login=LOGIN):
    repos = []
    after = None
    while True:
        conn = gql(REPOS_QUERY, {"login": login, "after": after})["user"]["repositories"]
        repos.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            return repos
        after = conn["pageInfo"]["endCursor"]


def fetch_pr_nodes(gql, login=LOGIN):
    nodes = []
    after = None
    q = f"is:pr is:merged author:{login} -user:{login}"
    while True:
        conn = gql(PRS_QUERY, {"q": q, "after": after})["search"]
        nodes.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            return nodes
        after = conn["pageInfo"]["endCursor"]


def aggregate_langs(repos, top=6):
    """Sum language bytes over owned non-fork repos; top N as [name, percent]."""
    sizes = {}
    for repo in repos:
        if repo.get("isFork"):
            continue
        for edge in (repo.get("languages") or {}).get("edges", []):
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
    total = sum(sizes.values())
    if not total:
        return []
    ranked = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return [[name, size / total * 100] for name, size in ranked]


def aggregate_prs(nodes, login=LOGIN, min_stars=MIN_STARS):
    """Count merged PRs per repo; keep public repos not owned by `login` with
    at least `min_stars` stars. Returns [repo, stars, count] sorted by count
    desc, then stars desc."""
    counts, star_count = {}, {}
    for node in nodes:
        repo = (node or {}).get("repository")
        if not repo or repo.get("isPrivate"):
            continue
        if repo["owner"]["login"].lower() == login.lower():
            continue
        if repo["stargazerCount"] < min_stars:
            continue
        name = repo["nameWithOwner"]
        counts[name] = counts.get(name, 0) + 1
        star_count[name] = repo["stargazerCount"]
    ranked = sorted(counts, key=lambda n: (-counts[n], -star_count[n], n))
    return [[n, star_count[n], counts[n]] for n in ranked]


def build_data(token, fallback=None, now=None):
    now = now or datetime.now(timezone.utc)
    graph = load_graph_module()
    days = graph.fetch_contributions()
    all_days, total = graph.fetch_all_contributions()
    total, streak, best = graph.compute_streak_stats(all_days, total)
    gql = GraphQL(token, fallback)
    langs = aggregate_langs(fetch_repos(gql))
    oss = aggregate_prs(fetch_pr_nodes(gql))
    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    return {
        "login": LOGIN,
        "name": NAME,
        "total": total,
        "streak": streak,
        "best": best,
        "days_from": month_day(days[0][0]),
        "days": [c for _, c in days],
        "langs": langs,
        "oss": oss,
        "tokens": {
            "total": tokens["total"],
            "since": month_year(tokens["since"]),
            "synced": month_day(tokens["updated"], LOCAL_TZ),
        },
        "stack": load_stack(),
        "generated_at": now,
    }


# The lab's DATA values, so the fixture render matches its terminal view.
FIXTURE = {
    "total": 5280, "streak": 2, "best": 109,
    "days_from": "aug 30",
    "days": [4, 40, 24, 65, 67, 17, 62, 68, 28, 10, 18, 61, 39, 9, 6, 94, 20, 51, 72, 80, 47, 5, 127, 97, 65, 19, 294, 0, 159, 90, 0],
    "langs": [["TypeScript", 45.40], ["Python", 27.03], ["Shell", 9.49], ["Rust", 7.22], ["Swift", 6.03], ["JavaScript", 4.84]],
    "oss": [
        ["rocketride-org/rocketride-server", 17334, 81], ["run-llama/llama_index", 52344, 3], ["better-auth/better-auth", 30120, 3],
        ["c15t/c15t", 1919, 2], ["modelcontextprotocol/servers", 90653, 1], ["InsForge/InsForge", 13025, 1], ["qdrant/landing_page", 60, 1],
    ],
    "tokens": {"total": 75846214525, "since": "dec 2025", "synced": "sep 29"},
    "generated_at": datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc),
}


def fixture_data():
    data = dict(FIXTURE)
    data.update(login=LOGIN, name=NAME, stack=load_stack())
    return data


def summary(data):
    days = data["days"]
    langs = ", ".join(f"{n} {to_fixed(v, 1)}%" for n, v in data["langs"])
    oss = ", ".join(f"{repo} {n} ({st}★)" for repo, st, n in data["oss"])
    tk = data["tokens"]
    return "\n".join([
        f"contributions: {data['total']:,} total, streak {data['streak']}, best {data['best']}, "
        f"{sum(days):,} in the last {len(days)} days from {data['days_from']}",
        f"languages: {langs}",
        f"merged prs: {sum(r[2] for r in data['oss'])} across {len(data['oss'])} repos: {oss}",
        f"tokens: {tk['total']:,} since {tk['since']}, synced {tk['synced']}",
        f"stack: {sum(len(g) for row in data['stack']['rows'] for g in row)} tools",
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render assets/readme.svg for the profile README.")
    ap.add_argument("--fixture", action="store_true", help="render the built-in sample data, no network")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help=f"output path (default {OUT_PATH})")
    args = ap.parse_args(argv)

    if args.fixture:
        data = fixture_data()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        # Any exception here propagates: the Action exits non-zero and keeps the previous card.
        data = build_data(token, os.environ.get("GITHUB_FALLBACK_TOKEN") or None)

    svg = render(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg + "\n", encoding="utf-8")
    print(summary(data))
    print(f"wrote {args.out} ({len(svg.encode('utf-8')) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
