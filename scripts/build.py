#!/usr/bin/env python3
"""Build script for the "Surface You Test" project page.

Reads the camera-ready paper source, then:
  1. converts paper figures to WebP under static/img/figures/
  2. renders the paper's tables as HTML fragments and injects them into
     index.html between <!-- @build:NAME --> markers.

Every number is parsed from the paper's LaTeX, so nothing on the page is
retyped by hand.

Usage:  python3 scripts/build.py
"""
import html
import re
from pathlib import Path

from PIL import Image

SITE = Path(__file__).resolve().parent.parent
PAPER_DIR = SITE.parent / "Prompt-Injection-NeurIPS-Workshop-final"
PAPER_TEX = PAPER_DIR / "neurips_2026.tex"
APPENDIX_TEX = PAPER_DIR / "appendix.tex"

FIG_OUT = SITE / "static/img/figures"

FIGURES = [
    "main.png",
    "01_ranking_scatter.png",
    "02_em_fsr.png",
    "03_loso.png",
    "07_heatmap.png",
]

SUITES = ["Banking", "Slack", "Travel", "Workspace"]

# (marker, table label, columns whose numbers get a heat shade)
PAPER_TABLES = [
    ("inversion", "tab:inversion", {}),
    ("decomposition", "tab:decomposition", {}),
    ("loso", "tab:loso", {}),
    ("defenses", "tab:defenses", {"Data ASR": "red", "Schema ASR": "red"}),
    ("native", "tab:mcp", {"Data ASR": "red", "Schema ASR": "red"}),
    ("payload", "tab:payload-ablation", {"Schema ASR": "red"}),
    ("selection", "tab:selection", {}),
]


# ----------------------------------------------------------------------------
# LaTeX parsing
# ----------------------------------------------------------------------------
def table_block(tex, label):
    """Return the tabular body of the table carrying \\label{label}."""
    at = tex.index(rf"\label{{{label}}}")
    start = tex.index(r"\begin{tabular}", at)
    end = tex.index(r"\end{tabular}", start)
    return tex[start:end]


def latex_to_html(s):
    s = re.sub(r"(?<!\\)%.*$", "", s)  # drop trailing comments (e.g. "% chktex 8"), keep \%
    s = s.replace(r"\%", "%").replace(r"\_", "_").replace(r"\ ", " ").replace("~", " ")
    s = s.replace("$-$", "−").replace("---", "—").replace("--", "–")
    s = s.replace(r"$\Delta$", "Δ").replace(r"\quad", "")
    s = re.sub(r"\$\\Delta_\{\\mathrm\{surface\}\}\$", "Δ<sub>surface</sub>", s)
    s = re.sub(r"\$\\times\$", "×", s)
    s = html.escape(s, quote=False).replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    s = re.sub(r"\\textbf\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"<b>\1</b>", s)
    s = re.sub(r"\\texttt\{([^{}]*)\}", r"<code>\1</code>", s)
    s = re.sub(r"\\textsc\{([^{}]*)\}", r"\1", s)
    s = s.replace("$", "")
    return s.strip()


def parse_table(tex, label):
    """Parse a booktabs table into (header, groups-of-rows)."""
    block = table_block(tex, label)
    body = block.split(r"\toprule", 1)[1].split(r"\bottomrule", 1)[0]
    header, groups, cur = None, [], []
    for chunk in re.split(r"(\\midrule)", body):
        if chunk == r"\midrule":
            if cur:
                groups.append(cur)
            cur = []
            continue
        for line in chunk.split(r"\\"):
            line = re.sub(r"\\addlinespace(\[[^\]]*\])?", "", line)
            line = re.sub(r"(?<!\\)%.*$", "", line, flags=re.M).strip()
            if not line:
                continue
            raw = [c.strip() for c in line.split("&")]
            cells = [latex_to_html(c) for c in raw]
            indent = raw[0].startswith(r"\quad")
            if header is None:
                header = cells
            else:
                cur.append((cells, indent))
    if cur:
        groups.append(cur)
    return header, groups


def parse_percell(tex):
    """Complete model x suite results (appendix table tab:percell)."""
    block = table_block(tex, "tab:percell")
    rows = []
    for line in block.split(r"\\"):
        m = re.search(r"\\textsc\{([^}]*)\}\s*&\s*(\w+)\s*&(.*)$", line.strip(), re.S)
        if not m:
            continue
        c = [x.strip() for x in m.group(3).split("&")]
        # Recover exact rates from episode counts: the table rounds to 0.1pp,
        # and averaging rounded cells drifts from the paper's model means.
        nd, ns = int(c[1]), int(c[3])
        d = round(float(c[0]) * nd / 100) / nd * 100
        s = round(float(c[2]) * ns / 100) / ns * 100
        rows.append({"model": m.group(1), "suite": m.group(2),
                     "data": d, "schema": s, "worst": max(d, s)})
    return rows


def plain_number(cell):
    m = re.search(r"[−+]?\d+(?:\.\d+)?", re.sub(r"<[^>]+>", "", cell))
    return float(m.group(0).replace("−", "-")) if m else None


# ----------------------------------------------------------------------------
# Assets
# ----------------------------------------------------------------------------
def to_webp(src, dst, max_w, quality=88):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return Image.open(dst).size
    im = Image.open(src)
    im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    im.save(dst, "WEBP", quality=quality, method=6)
    return im.size


def build_figures():
    sizes = {}
    for f in FIGURES:
        sizes[Path(f).stem] = to_webp(PAPER_DIR / "figures" / f, FIG_OUT / (Path(f).stem + ".webp"), 1800)
    return sizes


# ----------------------------------------------------------------------------
# HTML rendering
# ----------------------------------------------------------------------------
e = html.escape


def signed(v):
    return "0.0" if round(v, 1) == 0 else f"{v:+.1f}".replace("-", "−")


def heat(v, kind="red"):
    if kind == "red":
        return f' class="heat" style="--a:{min(abs(v), 100) / 100 * 0.85:.2f}"'
    # diverging: positive = schema more vulnerable (red), negative = data (blue)
    cls = "div-pos" if v > 0 else "div-neg"
    return f' class="{cls}" style="--a:{min(abs(v), 100) / 100 * 0.8:.2f}"'


def render_paper_table(header, groups, heat_cols):
    heat_idx = {i: heat_cols[h] for i, h in enumerate(re.sub(r"<[^>]+>", "", x) for x in header) if h in heat_cols}
    head = "".join(f"<th>{h}</th>" for h in header)
    body = []
    for gi, group in enumerate(groups):
        for ri, (cells, indent) in enumerate(group):
            cls = []
            if ri == len(group) - 1 and gi < len(groups) - 1:
                cls.append("group-end")
            if indent:
                cls.append("sub")
            tds = []
            for ci, c in enumerate(cells):
                v = plain_number(c) if ci in heat_idx and "%" in c else None
                tds.append(f"<td{heat(v, heat_idx[ci]) if v is not None else ''}>{c}</td>")
            attr = f' class="{" ".join(cls)}"' if cls else ""
            body.append(f"<tr{attr}>{''.join(tds)}</tr>")
    return f'<table class="data"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def render_per_model(rows):
    """Model-level means over the four suites, sorted by signed surface gap."""
    models = {}
    for r in rows:
        models.setdefault(r["model"], []).append(r)
    out = []
    for name, cells in models.items():
        assert [c["suite"] for c in cells] == SUITES, name
        d = sum(c["data"] for c in cells) / 4
        s = sum(c["schema"] for c in cells) / 4
        w = sum(c["worst"] for c in cells) / 4
        out.append({"model": name, "data": d, "schema": s, "worst": w, "cells": cells})
    out.sort(key=lambda m: m["schema"] - m["data"], reverse=True)

    head = ("<tr><th rowspan=\"2\">Model</th><th colspan=\"3\">Mean over suites</th>"
            "<th colspan=\"4\">Δ<sub>surface</sub> = schema − data (pp)</th></tr>"
            "<tr><th>Data ASR</th><th>Schema ASR</th><th>Worst ASR</th>"
            + "".join(f"<th>{s}</th>" for s in SUITES) + "</tr>")
    body = []
    for m in out:
        gaps = "".join(f"<td{heat(c['schema'] - c['data'], 'div')}>{signed(c['schema'] - c['data'])}</td>"
                       for c in m["cells"])
        body.append(f'<tr><th class="model">{e(m["model"])}</th>'
                    f'<td{heat(m["data"])}>{m["data"]:.1f}</td>'
                    f'<td{heat(m["schema"])}>{m["schema"]:.1f}</td>'
                    f'<td>{m["worst"]:.1f}</td>{gaps}</tr>')
    table = (f'<table class="data per-model"><thead>{head}</thead>'
             f'<tbody>{"".join(body)}</tbody></table>')
    return table, out


def inject(page, name, fragment):
    pat = re.compile(rf"(<!-- @build:{name} -->)(.*?)(<!-- /@build:{name} -->)", re.S)
    if not pat.search(page):
        raise KeyError(f"marker {name} missing from index.html")
    return pat.sub(lambda m: m.group(1) + "\n" + fragment + "\n" + m.group(3), page)


def main():
    tex = PAPER_TEX.read_text() + "\n" + APPENDIX_TEX.read_text()
    sizes = build_figures()

    index = SITE / "index.html"
    page = index.read_text()
    for marker, label, heat_cols in PAPER_TABLES:
        header, groups = parse_table(tex, label)
        page = inject(page, marker, render_paper_table(header, groups, heat_cols))

    percell = parse_percell(tex)
    assert len(percell) == 52, len(percell)
    per_model_html, per_model = render_per_model(percell)
    page = inject(page, "per-model", per_model_html)
    index.write_text(page)

    by = {m["model"]: m for m in per_model}
    g, o = by["Gemini-3-Flash"], by["GPT-4.1"]
    print(f"figures={sorted(sizes)} cells={len(percell)} models={len(per_model)}")
    print(f"check: Gemini-3-Flash data {g['data']:.1f} / schema {g['schema']:.1f}; "
          f"GPT-4.1 data {o['data']:.1f} / schema {o['schema']:.1f}")


if __name__ == "__main__":
    main()
