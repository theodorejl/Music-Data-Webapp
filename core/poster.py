"""A3 landscape poster (PDF) of album covers in a grid, with a caption under each
cover: album title, release date, artist. The grid is chosen so that covers are as
large as possible while all albums fit on one page."""

from __future__ import annotations

import io
import math
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A3)  # points (1/72 inch): 420 x 297 mm
MARGIN = 10 * mm
CAPTION_LINES = 3
CAPTION_RATIO = 0.075  # font size relative to cover size
LINE_SPACING = 1.25
GAP_RATIO = 0.10  # horizontal gap relative to cover size


@dataclass
class Layout:
    cols: int
    rows: int
    cover: float  # points
    font: float  # points
    cell_w: float
    cell_h: float


def best_layout(n: int, width: float = PAGE_W - 2 * MARGIN, height: float = PAGE_H - 2 * MARGIN,
                title_h: float = 0.0) -> Layout:
    """Try every column count and keep the one giving the biggest covers."""
    height -= title_h
    best = None
    for cols in range(1, max(1, n) + 1):
        rows = math.ceil(max(1, n) / cols)
        cell_w, cell_h = width / cols, height / rows
        # cover + gap must fit the width; cover + caption + gap must fit the height.
        by_w = cell_w / (1 + GAP_RATIO)
        by_h = cell_h / (1 + CAPTION_LINES * CAPTION_RATIO * LINE_SPACING + GAP_RATIO)
        cover = min(by_w, by_h)
        if best is None or cover > best.cover:
            best = Layout(cols, rows, cover, max(2.5, cover * CAPTION_RATIO), cell_w, cell_h)
    return best


def _latin(text: str) -> str:
    """Keep characters the built-in PDF fonts can draw (accents OK, other scripts -> '?')."""
    text = unicodedata.normalize("NFC", str(text or ""))
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _fit(text: str, font: str, size: float, max_w: float) -> str:
    text = _latin(text)
    if stringWidth(text, font, size) <= max_w:
        return text
    while text and stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _fetch(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        return r.content if r.ok else None
    except requests.RequestException:
        return None


def album_poster_pdf(albums: list[dict], title: str | None = None) -> bytes:
    """albums: [{"title", "artist", "release" (text), "cover_url"}] in display order."""
    n = len(albums)
    title_h = 14 * mm if title else 0
    layout = best_layout(n, title_h=title_h)
    # Higher resolution covers only when they are printed big.
    size_key = "cover_url_big" if layout.cover > 60 * mm else "cover_url"
    with ThreadPoolExecutor(16) as pool:
        images = list(pool.map(lambda a: _fetch(a.get(size_key) or a.get("cover_url")), albums))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(_latin(title or "Albums"))
    if title:
        c.setFont("Helvetica-Bold", 20)
        c.drawString(MARGIN, PAGE_H - MARGIN - 16, _latin(title))

    grid_w = layout.cols * layout.cell_w
    x0 = (PAGE_W - grid_w) / 2  # center the grid horizontally
    top = PAGE_H - MARGIN - title_h
    f = layout.font
    for i, (album, img) in enumerate(zip(albums, images)):
        row, col = divmod(i, layout.cols)
        cx = x0 + col * layout.cell_w + (layout.cell_w - layout.cover) / 2
        cy = top - row * layout.cell_h - layout.cover
        if img:
            try:
                c.drawImage(ImageReader(io.BytesIO(img)), cx, cy, layout.cover, layout.cover)
            except Exception:
                img = None
        if not img:
            c.setFillGray(0.9)
            c.rect(cx, cy, layout.cover, layout.cover, stroke=0, fill=1)
        c.setFillGray(0)
        lines = [("Helvetica-Bold", album.get("title")), ("Helvetica", album.get("release")),
                 ("Helvetica", album.get("artist"))]
        y = cy - f * LINE_SPACING
        for font, text in lines:
            c.setFont(font, f)
            c.drawString(cx, y, _fit(text or "", font, f, layout.cover))
            y -= f * LINE_SPACING
    c.showPage()
    c.save()
    return buf.getvalue()
