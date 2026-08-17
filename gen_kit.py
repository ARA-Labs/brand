#!/usr/bin/env python3
"""Generate the ARA Lab vector logo kit.

The `{A}` mark is a potrace vector trace of the original production
raster (`source/brace-a_mark.png`, brand-direction.md §Final lockup) —
NOT a font reconstruction, so brace weight, modulation, and the A's
letterform match the approved mark exactly. The peach square is rebuilt
as an exact <rect> at the raster's measured position. The lockups pair
the traced mark with an "ARA LAB" wordmark set in American Typewriter
(regular), letterspaced caps — chosen 2026-08-16 over the earlier Didot
bold wordmark, and set singular ("Lab", not "Labs") from 2026-08-16.

Run:  python3 gen_kit.py            # full kit (SVG + PNG via headless Chrome)
      python3 gen_kit.py --svg-only
Requires: potrace (brew), fontTools, Pillow, Google Chrome.
Outputs land in out/.
Palette per brand-direction.md: deep ink #1a1530, warm peach #e8a878.
"""

import os
import re
import subprocess
import sys

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTCollection
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RASTER = os.path.join(HERE, "source/brace-a_mark.png")
FONT = "/System/Library/Fonts/Supplemental/AmericanTypewriter.ttc"
FONT_INDEX = 0  # American Typewriter regular
TEXT = "ARA LAB"                 # wordmark: letterspaced caps
SLUG = "ara-lab"                 # output filename stem
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

INK = "#1a1530"
PEACH = "#e8a878"
WHITE = "#ffffff"

# measured on the 1024px raster
SQUARE = (782, 392, 62)          # x, y, side of the peach square
SQUARE_EXCLUDE = (776, 386, 850, 460)  # region masked out before tracing
CONTENT = (231, 281, 844, 742)   # ink+square bbox: x0, y0, x1, y1
A_BASELINE = 646                 # baseline of the A inside the mark
A_CAP = 269                      # its cap height

# lockup tunables (raster px units)
WORD_GAP = 78                    # gap between mark content edge and wordmark
WORD_CAP = 272                   # wordmark cap height reference
TRACK = 60                       # wordmark letter tracking, raster px
SPACE = 110                      # width of the word space
V_GAP = 84                       # vertical lockup: gap between mark and wordmark


def trace_mark_path():
    """Trace the raster's ink (square masked out) with potrace; return
    (path_d, potrace_transform)."""
    img = Image.open(RASTER).convert("RGBA")
    ink = np.array(img)[..., 3] > 128
    x0, y0, x1, y1 = SQUARE_EXCLUDE
    ink[y0:y1, x0:x1] = False
    h, w = ink.shape
    pbm = os.path.join(OUT, "ink.pbm")
    with open(pbm, "wb") as f:
        f.write(f"P4\n{w} {h}\n".encode())
        f.write(np.packbits(ink.astype(np.uint8), axis=1).tobytes())
    traced = os.path.join(OUT, "ink-traced.svg")
    subprocess.run(["potrace", pbm, "-s", "-o", traced, "--flat",
                    "-t", "8", "-O", "0.4"], check=True)
    svg = open(traced).read()
    d = " ".join(re.findall(r'd="([^"]+)"', svg))
    tf = re.search(r'transform="([^"]+)"', svg).group(1)
    os.remove(pbm)
    os.remove(traced)
    return d, tf


def svg_doc(x0, y0, x1, y1, body, pad=0.06):
    w, h = x1 - x0, y1 - y0
    p = max(w, h) * pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{x0 - p:.1f} {y0 - p:.1f} {w + 2 * p:.1f} {h + 2 * p:.1f}">'
            f'{body}</svg>')


def mark_body(path_d, tf, ink):
    sx, sy, ss = SQUARE
    return (f'<g fill="{ink}" transform="{tf}"><path d="{path_d}"/></g>'
            f'<rect x="{sx}" y="{sy}" width="{ss}" height="{ss}" fill="{PEACH}"/>')


def build_mark(path_d, tf, ink):
    x0, y0, x1, y1 = CONTENT
    return svg_doc(x0, y0, x1, y1, mark_body(path_d, tf, ink))


class Face:
    def __init__(self, path=FONT, index=FONT_INDEX):
        self.font = TTCollection(path).fonts[index]
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()

    def glyph(self, ch):
        g = self.glyphs[self.cmap[ord(ch)]]
        sp = SVGPathPen(self.glyphs)
        g.draw(sp)
        bp = BoundsPen(self.glyphs)
        g.draw(bp)
        return sp.getCommands(), g.width, bp.bounds


def layout_word(face, cap, text):
    """Lay out `text` at cap height `cap`; tracking and word space scale
    with the cap so proportions hold at any size. Returns
    ([(x_offset, path_d, glyph_scale)], total_width)."""
    _, _, b_a = face.glyph("A")
    s = cap / (b_a[3] - b_a[1])        # font units -> raster px
    f = cap / WORD_CAP
    els, x = [], 0.0
    for ch in text:
        if ch == " ":
            x += SPACE * f
            continue
        d, adv, _ = face.glyph(ch)
        els.append((x, d, s))
        x += adv * s + TRACK * f
    return els, x - TRACK * f


def word_group(els, dx, baseline, ink):
    return (f'<g fill="{ink}">' +
            "".join(f'<g transform="translate({dx + ex:.1f},{baseline:.1f}) '
                    f'scale({es:.4f},{-es:.4f})"><path d="{d}"/></g>'
                    for ex, d, es in els) + '</g>')


def build_lockup(path_d, tf, face, ink, text=TEXT):
    x0, y0, x1, y1 = CONTENT
    els, w = layout_word(face, WORD_CAP, text)
    body = mark_body(path_d, tf, ink) + word_group(els, x1 + WORD_GAP,
                                                   A_BASELINE, ink)
    return svg_doc(x0, y0, x1 + WORD_GAP + w, y1, body)


def build_lockup_vertical(path_d, tf, face, ink, text=TEXT):
    """Stacked lockup: mark on top, wordmark centered beneath, sized so
    the wordmark spans the mark's width."""
    x0, y0, x1, y1 = CONTENT
    mark_w = x1 - x0
    _, w_ref = layout_word(face, WORD_CAP, text)
    cap = WORD_CAP * mark_w / w_ref
    els, w = layout_word(face, cap, text)
    baseline = y1 + V_GAP + cap
    body = mark_body(path_d, tf, ink) + word_group(els, x0 + (mark_w - w) / 2,
                                                   baseline, ink)
    return svg_doc(x0, y0, x1, baseline, body)


def export_png(svg_path, png_path, width, height):
    html = svg_path + ".export.html"
    with open(html, "w") as f:
        f.write(f'<!doctype html><body style="margin:0;background:transparent">'
                f'<img src="{os.path.basename(svg_path)}" '
                f'style="width:{width}px;height:{height}px;display:block">')
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    f"--screenshot={png_path}",
                    f"--window-size={width},{height}",
                    "--default-background-color=00000000",
                    "--hide-scrollbars", f"file://{html}"],
                   check=True, capture_output=True)
    os.remove(html)


def aspect(svg_path):
    vb = re.search(r'viewBox="([-\d. ]+)"', open(svg_path).read()).group(1).split()
    return float(vb[2]) / float(vb[3])


def main():
    os.makedirs(OUT, exist_ok=True)
    path_d, tf = trace_mark_path()
    face = Face()
    files = {
        f"{SLUG}-mark.svg": build_mark(path_d, tf, INK),
        f"{SLUG}-mark-white.svg": build_mark(path_d, tf, WHITE),
        f"{SLUG}-lockup-horizontal.svg": build_lockup(path_d, tf, face, INK),
        f"{SLUG}-lockup-horizontal-white.svg": build_lockup(path_d, tf, face, WHITE),
        f"{SLUG}-lockup-vertical.svg": build_lockup_vertical(path_d, tf, face, INK),
        f"{SLUG}-lockup-vertical-white.svg": build_lockup_vertical(path_d, tf, face, WHITE),
    }
    for name, svg in files.items():
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg)
    if "--svg-only" in sys.argv:
        return
    for base, sizes in [(f"{SLUG}-mark", [1024, 512, 256, 128, 64, 32]),
                        (f"{SLUG}-mark-white", [1024, 512]),
                        (f"{SLUG}-lockup-horizontal", [2400, 1200, 600]),
                        (f"{SLUG}-lockup-horizontal-white", [2400, 1200]),
                        (f"{SLUG}-lockup-vertical", [1600, 800, 400]),
                        (f"{SLUG}-lockup-vertical-white", [1600, 800])]:
        svg = os.path.join(OUT, base + ".svg")
        ar = aspect(svg)
        for s in sizes:
            export_png(svg, os.path.join(OUT, f"{base}-{s}.png"), s, round(s / ar))
    print("done:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
