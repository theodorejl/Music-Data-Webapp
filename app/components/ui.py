"""Reusable blocks of the "Noto" direction: stat tiles, illustrated rankings, podium, cover
mosaic, waffle, recent rows, a day in covers, cover wall, and the line-art pieces of the
page headers (giant figure, flowing line, fanned covers, faces, clock)."""

from __future__ import annotations

import math
from html import escape

import pandas as pd
import streamlit as st

from app.components import theme
from app.i18n import fmt_duration, fmt_int, fmt_plays, t

# Pages registry, filled by the shell so components can link to detail pages.
PAGES: dict[str, st.Page] = {}


def inject_css() -> None:
    theme.inject()


def _img(url, cls: str = "") -> str:
    if isinstance(url, str) and url:
        return f"<img src='{escape(url)}' alt='' loading='lazy'{f' class={cls!r}' if cls else ''}>"
    return "<div class='ds-noart'></div>"


def _family(i: int) -> str:
    return theme.ORDER[i % len(theme.ORDER)]


# --- small svg pieces -----------------------------------------------------------------------

def _smooth_path(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom through the points, as cubic Béziers."""
    if len(points) < 2:
        return ""
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def spark_svg(values, color: str = "currentColor", kind: str = "bars") -> str:
    vals = [float(v) for v in values][-28:]
    if not vals or max(vals) <= 0:
        return ""
    top = max(vals)
    w, h, n = 200, 34, len(vals)
    if kind == "line":
        pts = [(i * w / max(1, n - 1), h - 3 - (h - 6) * v / top) for i, v in enumerate(vals)]
        return (f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none'><path d='{_smooth_path(pts)}' fill='none' "
                f"stroke='{color}' stroke-width='2.5' stroke-linecap='round' vector-effect='non-scaling-stroke'/></svg>")
    bw = w / n
    bars = "".join(
        f"<rect x='{i * bw + bw * 0.18:.1f}' y='{h - max(2, (h - 2) * v / top):.1f}' width='{bw * 0.64:.1f}' "
        f"height='{max(2, (h - 2) * v / top):.1f}' rx='{min(3, bw * 0.3):.1f}' fill='{color}' opacity='{0.35 + 0.65 * v / top:.2f}'/>"
        for i, v in enumerate(vals))
    return f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none'>{bars}</svg>"


def art_giant(value: str, unit: str = "", caption: str = "") -> str:
    """Oversized figure, as the giant letters of the Noto panels."""
    html = f"<div class='ds-giant num'>{escape(value)}{f'<small>{escape(unit)}</small>' if unit else ''}</div>"
    if caption:
        html += f"<div class='ds-giant-cap'>{escape(caption)}</div>"
    return html


def art_line(values, caption: str = "", label_start: str = "", label_end: str = "") -> str:
    """A big hand-drawn-looking line of the values in the panel's deep ink, ending on a dot."""
    vals = [float(v) for v in values]
    if len(vals) < 2 or max(vals) <= 0:
        return ""
    top = max(vals)
    w, h = 560, 220
    pts = [(10 + i * (w - 20) / (len(vals) - 1), h - 16 - (h - 40) * v / top) for i, v in enumerate(vals)]
    area = _smooth_path(pts) + f" L{pts[-1][0]:.1f},{h} L{pts[0][0]:.1f},{h} Z"
    x_end, y_end = pts[-1]
    i_max = max(range(len(vals)), key=vals.__getitem__)
    xm, ym = pts[i_max]
    svg = (f"<svg viewBox='0 0 {w} {h + 28}'>"
           f"<path d='{area}' fill='currentColor' opacity='.08'/>"
           f"<path d='{_smooth_path(pts)}' fill='none' stroke='currentColor' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/>"
           f"<circle cx='{xm:.1f}' cy='{ym:.1f}' r='9' fill='#fff' stroke='currentColor' stroke-width='4'/>"
           f"<circle cx='{x_end:.1f}' cy='{y_end:.1f}' r='7' fill='currentColor'/>"
           f"<text x='10' y='{h + 24}' font-size='14' fill='currentColor' opacity='.8'>{escape(label_start)}</text>"
           f"<text x='{w - 10}' y='{h + 24}' font-size='14' text-anchor='end' fill='currentColor' opacity='.8'>{escape(label_end)}</text>"
           "</svg>")
    return svg + (f"<div class='ds-giant-cap'>{escape(caption)}</div>" if caption else "")


def art_fan(urls: list[str]) -> str:
    """Up to five covers fanned like a hand of cards."""
    urls = [u for u in urls if isinstance(u, str) and u][:5]
    if not urls:
        return ""
    n = len(urls)
    imgs = []
    for i, u in enumerate(urls):
        k = i - (n - 1) / 2
        imgs.append(f"<img src='{escape(u)}' alt='' style='left:calc(50% - 95px + {k * 74:.0f}px);"
                    f"transform:rotate({k * 7:.0f}deg) translateY({abs(k) * 12:.0f}px);z-index:{10 - int(abs(k) * 2)}'>")
    return f"<div class='ds-fan'>{''.join(imgs)}</div>"


def art_faces(urls: list[str], size: int = 300) -> str:
    """Artist photos in a loose cluster of circles (largest first)."""
    urls = [u for u in urls if isinstance(u, str) and u][:7]
    if not urls:
        return ""
    spots = [(50, 46, 44), (18, 26, 24), (82, 24, 22), (16, 76, 20), (84, 74, 24), (50, 92, 15), (34, 6, 13)]
    out = []
    for u, (x, y, r) in zip(urls, spots):
        out.append(f"<img src='{escape(u)}' alt='' style='position:absolute;left:{x - r / 2:.0f}%;top:{y - r / 2:.0f}%;"
                   f"width:{r:.0f}%;aspect-ratio:1;border-radius:50%;object-fit:cover;border:4px solid rgba(255,255,255,.85);"
                   f"box-shadow:0 20px 40px -24px rgba(0,0,0,.6)'>")
    return f"<div style='position:relative;width:100%;max-width:{size + 140}px;aspect-ratio:1.25;margin:0 auto'>{''.join(out)}</div>"


def art_clock(by_hour: pd.Series, caption: str = "") -> str:
    """A 24-petal line-art clock in the panel's ink."""
    vals = by_hour.reindex(range(24), fill_value=0).astype(float)
    top = float(vals.max()) or 1.0
    cx = cy = 150
    petals = []
    for h, v in vals.items():
        a = math.radians(h * 15 - 90 + 7.5)
        r0, r1 = 46, 46 + 92 * math.sqrt(v / top)
        x0, y0 = cx + r0 * math.cos(a), cy + r0 * math.sin(a)
        x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
        petals.append(f"<line x1='{x0:.1f}' y1='{y0:.1f}' x2='{x1:.1f}' y2='{y1:.1f}' stroke='currentColor' "
                      f"stroke-width='9' stroke-linecap='round' opacity='{0.35 + 0.65 * v / top:.2f}'/>")
    ticks = "".join(f"<text x='{cx + 30 * math.cos(math.radians(h * 15 - 90)):.0f}' y='{cy + 30 * math.sin(math.radians(h * 15 - 90)) + 4:.0f}' "
                    f"font-size='11' text-anchor='middle' fill='currentColor'>{h}</text>" for h in (0, 6, 12, 18))
    svg = (f"<svg viewBox='0 0 300 300' style='max-width:340px;margin:0 auto'>"
           f"<circle cx='{cx}' cy='{cy}' r='142' fill='none' stroke='currentColor' stroke-width='1.5' opacity='.25'/>"
           f"{''.join(petals)}{ticks}</svg>")
    return svg + (f"<div class='ds-giant-cap' style='text-align:center'>{escape(caption)}</div>" if caption else "")


# --- tiles and rankings ------------------------------------------------------------------------

def stat_tiles(items: list[tuple]) -> None:
    """items: (label, value, caption, family, spark values or None). The value may end with a
    unit after a "|" (e.g. "38|h"), shown smaller."""
    cells = []
    for i, item in enumerate(items):
        label, value, cap = item[0], str(item[1]), item[2] if len(item) > 2 else None
        family = item[3] if len(item) > 3 and item[3] else _family(i)
        spark = item[4] if len(item) > 4 else None
        main, _, unit = value.partition("|")
        cells.append(
            f"<div class='ds-panel ds-tile ds-fam-{family}'><div><div class='ds-tile-label'>{escape(label)}</div>"
            f"<div class='ds-tile-value num'>{escape(main)}{f'<small>{escape(unit)}</small>' if unit else ''}</div>"
            + (f"<div class='ds-tile-cap'>{escape(cap)}</div>" if cap else "") + "</div>"
            + (f"<div style='color:{theme.ink(family)}'>{spark_svg(spark)}</div>" if spark is not None else "") + "</div>")
    theme.html(f"<div class='ds-tiles'>{''.join(cells)}</div>")


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    stat_tiles([(label, value, cap) for label, value, cap in items])


def rank_list(items: pd.DataFrame, value_fmt, metric: str = "plays", colors: list[str] | None = None,
              round_art: bool = False, limit: int = 8, start: int = 1, scale_max: float | None = None) -> None:
    """Ranking rows: big rank number, artwork, name and detail, and a gradient bar in the item's
    own colour (genre colour when given, else the palette in order)."""
    rows = list(items.head(limit).itertuples(index=False))
    if not rows:
        return
    top = scale_max or max(float(getattr(r, metric)) for r in rows) or 1
    html = []
    for i, r in enumerate(rows):
        color = (colors[i] if colors and i < len(colors) else theme.PALETTE[i % len(theme.PALETTE)])
        width = max(3.0, 100.0 * float(getattr(r, metric)) / top)
        sub = escape(r.sublabel) if isinstance(r.sublabel, str) and r.sublabel else ""
        html.append(
            f"<div class='ds-rank-row{' round' if round_art else ''}'><div class='ds-rank-n num'>{i + start}</div>{_img(r.image)}"
            f"<div style='min-width:0'><div class='ds-rank-line'><b>{escape(str(r.label))}</b>"
            f"<span class='num'>{escape(value_fmt(r))}</span></div>"
            + (f"<div class='ds-rank-sub'>{sub}</div>" if sub else "")
            + f"<div class='ds-rank-bar'><i style='width:{width:.1f}%;background:linear-gradient(90deg,{color}55,{color})'></i></div>"
            "</div></div>")
    st.html(f"<div class='ds-rank'>{''.join(html)}</div>")


def bar_list(items: pd.DataFrame, value_fmt, round_art: bool = False, limit: int = 6, metric: str = "plays") -> None:
    rank_list(items, value_fmt, metric, round_art=round_art, limit=limit)


def podium(items: pd.DataFrame, value_fmt, kind: str | None, key: str, round_art: bool = False) -> None:
    """The top three on pedestals (2 · 1 · 3), artwork large, each opens its page."""
    rows = list(items.head(3).itertuples(index=False))
    if not rows:
        return
    order = [1, 0, 2] if len(rows) == 3 else list(range(len(rows)))
    heights = {0: 96, 1: 64, 2: 46}
    families = {0: "coral", 1: "sky", 2: "lilac"}
    cols = st.columns([1, 1.18, 1][:len(order)] if len(order) == 3 else len(order), gap="medium", vertical_alignment="bottom")
    for col, i in zip(cols, order):
        r = rows[i]
        with col:
            st.html(f"<div class='ds-pod{' round' if round_art else ''}'>{_img(r.image)}<b>{escape(str(r.label))}</b>"
                    f"<span>{escape(r.sublabel) + ' · ' if isinstance(r.sublabel, str) and r.sublabel else ''}{escape(value_fmt(r))}</span>"
                    f"<div class='ds-panel ds-pod-base ds-fam-{families[i]}' style='height:{heights[i]}px'>{i + 1}</div></div>")
            if kind and st.button(t("common.open_page"), key=f"{key}_pod_{i}", type="tertiary", icon=":material/arrow_outward:"):
                open_detail(kind, r.key)


def _squarify(areas: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    def worst(row, length):
        s = sum(row)
        return max(length * length * max(row) / (s * s), s * s / (length * length * min(row)))

    def place(row, x, y, w, h):
        s = sum(row)
        out = []
        if w >= h:
            rw = s / h
            yy = y
            for a in row:
                out.append((x, yy, rw, a / rw))
                yy += a / rw
            return out, (x + rw, y, w - rw, h)
        rh = s / w
        xx = x
        for a in row:
            out.append((xx, y, a / rh, rh))
            xx += a / rh
        return out, (x, y + rh, w, h - rh)

    rects, row, i = [], [], 0
    while i < len(areas):
        a = areas[i]
        length = min(w, h)
        if not row or worst(row + [a], length) <= worst(row, length):
            row.append(a)
            i += 1
        else:
            out, (x, y, w, h) = place(row, x, y, w, h)
            rects += out
            row = []
    if row:
        rects += place(row, x, y, w, h)[0]
    return rects


def mosaic(items: pd.DataFrame, metric: str, value_fmt, ratio: float = 1.9, limit: int = 24) -> None:
    """Covers as a squarified treemap: each album's area is its share of the listening."""
    rows = [r for r in items.head(limit).itertuples(index=False) if float(getattr(r, metric)) > 0]
    if not rows:
        return
    vals = [float(getattr(r, metric)) for r in rows]
    W, H = 100.0, 100.0 / ratio
    total = sum(vals)
    rects = _squarify([v * W * H / total for v in vals], 0, 0, W, H)
    tiles = []
    for i, (r, (x, y, w, h)) in enumerate(zip(rows, rects)):
        share = vals[i] / total
        bg = (f"background-image:url({escape(r.image)})" if isinstance(r.image, str) and r.image
              else f"background:{theme.PALETTE[i % len(theme.PALETTE)]}")
        title = escape(f"{r.label} — {value_fmt(r)}")
        tiles.append(f"<div class='ds-tess{' big' if share > 0.05 else ''}' title='{title}' style='left:{x:.3f}%;top:{y / H * 100:.3f}%;"
                     f"width:{w:.3f}%;height:{h / H * 100:.3f}%;{bg}'><span><b>{escape(str(r.label))}</b><br>{escape(value_fmt(r))}</span></div>")
    st.html(f"<div class='ds-mosaic' style='aspect-ratio:{ratio}'>{''.join(tiles)}</div>")


def waffle(parts: list[tuple[str, float]], colors: dict[str, str], cells: int = 200, value_fmt=None) -> None:
    """Shares as a 20-wide grid of small squares, with a legend under it."""
    total = sum(v for _, v in parts) or 1
    counts = [max(0, round(cells * v / total)) for _, v in parts]
    diff = cells - sum(counts)
    if counts:
        counts[0] += diff
    squares = "".join(f"<i style='background:{colors[lab]}' title='{escape(lab)}'></i>" * n for (lab, _), n in zip(parts, counts))
    legend = "".join(f"<span><i style='background:{colors[lab]}'></i>{escape(lab)} <em>{value_fmt(v) if value_fmt else round(100 * v / total)}"
                     f"{'' if value_fmt else ' %'}</em></span>" for lab, v in parts)
    st.html(f"<div class='ds-waffle'>{squares}</div><div class='ds-legend'>{legend}</div>")


def legend(items: list[tuple[str, str]]) -> None:
    st.html("<div class='ds-legend'>" + "".join(f"<span><i style='background:{c}'></i>{escape(lab)}</span>" for lab, c in items) + "</div>")


# --- covers instead of dots ---------------------------------------------------------------------

def _bucket(dates: pd.Series) -> tuple[pd.Series, str]:
    span = (dates.max() - dates.min()).days if len(dates) else 0
    if span <= 21:
        return dates.dt.normalize(), "day"
    if span <= 140:
        return (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.normalize(), "week"
    return dates.dt.to_period("M").dt.to_timestamp(), "month"


def _bucket_label(d: pd.Timestamp, kind: str) -> str:
    from app.i18n import tl

    months = tl("months_short")
    if kind == "month":
        return f"{months[d.month - 1]} {str(d.year)[2:]}"
    return f"{d.day} {months[d.month - 1]}"


def cover_timeline(items: pd.DataFrame, date_col: str, value_fmt, per_col: int = 5, max_cols: int = 18,
                   round_art: bool = False) -> None:
    """Things grouped by day, week or month of `date_col`: each group is a column of covers (the
    most played at the bottom, "+n" when there are more), so every item stays readable."""
    d = items.dropna(subset=[date_col]).copy()
    if d.empty:
        return
    dates = pd.to_datetime(d[date_col])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    d["_b"], kind = _bucket(dates)
    groups = sorted(d["_b"].unique())[-max_cols:]
    cols = []
    for b in groups:
        g = d[d["_b"] == b].sort_values("plays", ascending=False)
        cells = []
        for r in g.head(per_col).itertuples(index=False):
            tip = escape(f"{r.label}{' — ' + r.sublabel if isinstance(r.sublabel, str) and r.sublabel else ''} · {value_fmt(r)}")
            cells.append(f"<img src='{escape(r.image)}' alt='{tip}' title='{tip}'>" if isinstance(r.image, str) and r.image
                         else f"<i title='{tip}'></i>")
        more = f"<span class='ds-ctl-more num'>+{len(g) - per_col}</span>" if len(g) > per_col else ""
        cols.append(f"<div class='ds-ctl-col'>{more}{''.join(reversed(cells))}"
                    f"<span class='ds-ctl-lab'>{escape(_bucket_label(pd.Timestamp(b), kind))}<b class='num'>{len(g)}</b></span></div>")
    st.html(f"<div class='ds-ctl{' round' if round_art else ''}'>{''.join(cols)}</div>")


def week_covers(matrix: pd.DataFrame, value_fmt) -> None:
    """Weekday × hour, each slot showing the cover of what played most there, sized by how much
    you listened, ringed with the colour of the moment of the day."""
    from app.components.charts import hour_color
    from app.i18n import tl

    days = tl("weekdays_short")
    top = float(matrix["value"].max()) if not matrix.empty else 1.0
    cells = {(int(r.weekday), int(r.hour)): r for r in matrix.itertuples(index=False)}
    head = "<span></span>" + "".join(f"<span class='ds-wk-h num'>{h if h % 3 == 0 else ''}</span>" for h in range(24))
    rows = [f"<div class='ds-wk-row'>{head}</div>"]
    for wd in range(7):
        out = [f"<span class='ds-wk-d'>{escape(days[wd])}</span>"]
        for h in range(24):
            r = cells.get((wd, h))
            if r is None or not r.value:
                out.append("<span class='ds-wk-c'><i></i></span>")
                continue
            size = 38 + 62 * math.sqrt(float(r.value) / top)
            tip = escape(f"{days[wd]} {h} h · {value_fmt(r.value)} · {r.title or ''} — {r.artist or ''}")
            ring = hour_color(h + 0.5)
            look = f"width:{size:.0f}%;height:{size:.0f}%;box-shadow:0 0 0 2px {ring}"
            if isinstance(r.cover, str) and r.cover:
                inner = f"<img src='{escape(r.cover)}' alt='' title='{tip}' style='{look}'>"
            else:
                inner = f"<b title='{tip}' style='{look};background:{ring}'></b>"
            out.append(f"<span class='ds-wk-c'>{inner}</span>")
        rows.append(f"<div class='ds-wk-row'>{''.join(out)}</div>")
    st.html(f"<div class='ds-wk'>{''.join(rows)}</div>")


def moments(parts: list[dict]) -> None:
    """Night, morning, afternoon, evening: minutes and the album that played most in each."""
    from app.i18n import t as tr

    fams = {"night": "lilac", "morning": "butter", "afternoon": "coral", "evening": "sky"}
    cards = []
    for m in parts:
        cover = _img(m["cover"])
        what = escape(f"{m['title']} — {m['artist']}") if m["title"] else "–"
        cards.append(f"<div class='ds-panel ds-moment ds-fam-{fams[m['name']]}'>{cover}<div><b>{escape(tr('moments.' + m['name']))}</b>"
                     f"<span class='num'>{escape(fmt_duration(m['minutes']))}</span><em>{what}</em></div></div>")
    st.html(f"<div class='ds-moments'>{''.join(cards)}</div>")


def item_colors(items: pd.DataFrame, dim: str, df: pd.DataFrame) -> list[str]:
    """Each ranked item in the colour of its genre (a genre keeps its colour everywhere)."""
    from app.components import charts, data

    if dim == "genre":
        genres = list(items["label"])
    elif dim == "artist":
        by = data.artist_genres()
        genres = [by.get(int(k)) for k in items["key"]]
    else:
        col = "album_id" if dim == "album" else "track_id"
        by = df.dropna(subset=["genre"]).drop_duplicates(col).set_index(col)["genre"].to_dict()
        genres = [by.get(k) for k in items["key"]]
    cmap = charts.category_colors([g for g in dict.fromkeys(genres) if g])
    return [cmap.get(g, charts.OTHER) for g in genres]


def ranking(df: pd.DataFrame, dim: str, metric: str, n: int) -> pd.DataFrame:
    """stats.top() with covers for every kind, genres included."""
    from core import stats

    items = stats.top(df, dim, metric, n)
    return with_genre_covers(items, df) if dim == "genre" and not items.empty else items


def with_genre_covers(items: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Give genre rows the cover of their most played album, and their leading artist."""
    from core import stats

    data = df.dropna(subset=["genre"])
    covers = stats.top_cover_by(data, data["genre"])
    out = items.copy()
    out["image"] = [covers.get(g, (None,))[0] for g in out["label"]]
    out["sublabel"] = [f"{covers[g][2]} · {covers[g][1]}" if g in covers else None for g in out["label"]]
    return out


# --- lists of plays -----------------------------------------------------------------------------

def short_rows(df: pd.DataFrame, limit: int = 5) -> None:
    """Recent plays: cover, title and artist, time and listened duration."""
    from app.i18n import fmt_seconds

    rows = []
    for r in df.head(limit).itertuples(index=False):
        rows.append(f"<div class='ds-row'>{_img(r.cover)}<div class='ds-row-main'><b>{escape(str(r.track_title))}</b>"
                    f"<span>{escape(str(r.artist_name))}</span></div>"
                    f"<div class='ds-row-end num'><b>{r.played_local.strftime('%H:%M')}</b>{fmt_seconds(r.listened_seconds)}"
                    f"{'*' if r.duration_is_estimated else ''}</div></div>")
    st.html(f"<div class='ds-rows'>{''.join(rows)}</div>")


def day_in_covers(df: pd.DataFrame, per_hour: int = 5) -> None:
    """One day's plays as their covers, one column per hour, stacked from the axis up."""
    by_hour: dict[int, list] = {}
    for r in df.sort_values("played_local").itertuples(index=False):
        by_hour.setdefault(r.played_local.hour, []).append(r)
    cols = []
    for h in range(24):
        plays = by_hour.get(h, [])
        cells = []
        for r in plays[-per_hour:]:
            tip = escape(f"{r.played_local:%H:%M} · {r.track_title} — {r.artist_name}")
            cells.append(f"<img src='{escape(r.cover)}' alt='{tip}' title='{tip}'>" if isinstance(r.cover, str) and r.cover
                         else f"<i title='{tip}'></i>")
        more = f"<span class='ds-day-more num'>+{len(plays) - per_hour}</span>" if len(plays) > per_hour else ""
        label = f"<span class='ds-day-h num'>{h} h</span>" if h % 3 == 0 else "<span class='ds-day-h'></span>"
        cols.append(f"<div class='ds-day-col'>{more}{''.join(reversed(cells))}{label}</div>")
    st.html(f"<div class='ds-day'>{''.join(cols)}</div>")


def wall(items: pd.DataFrame, caption_fmt, limit: int = 60) -> None:
    """A wall of covers with their names."""
    cells = []
    for r in items.head(limit).itertuples(index=False):
        cells.append(f"<a>{_img(r.image)}<b>{escape(str(r.label))}</b><span>{escape(caption_fmt(r))}</span></a>")
    st.html(f"<div class='ds-wall'>{''.join(cells)}</div>")


# --- states, navigation, tables -------------------------------------------------------------------

def header(title: str, subtitle: str | None = None, lead: str | None = None, dot: str | None = None) -> None:
    family = theme.PAGE_FAMILY.get(st.session_state.get("page", ""), "mist")
    theme.hero(family, title, escape(lead) if lead else None, subtitle)


def empty_state(message: str | None = None) -> None:
    st.info(message or t("common.no_data"))


def estimated_note(df: pd.DataFrame) -> None:
    if not df.empty and df["duration_is_estimated"].any():
        st.caption("ⓘ " + t("common.estimated_note"))


def open_detail(kind: str, key) -> None:
    page = PAGES.get(kind)
    if page is not None and key is not None and not pd.isna(key):
        st.switch_page(page, query_params={"id": str(int(key))})


def cover_grid(items: pd.DataFrame, kind: str | None, value_fmt, columns: int = 6, key: str = "grid") -> None:
    """Grid of covers; clicking a title opens the detail page."""
    columns = min(columns, 8)
    rows = list(items.itertuples(index=False))
    for start in range(0, len(rows), columns):
        cols = st.columns(columns)
        for col, row in zip(cols, rows[start:start + columns]):
            with col:
                st.html(f"<div class='ds-wall' style='grid-template-columns:1fr'><a>{_img(row.image)}</a></div>")
                label = str(row.label)
                if kind and st.button(f"{row.rank}. {label}", key=f"{key}_{kind}_{row.key}", type="tertiary",
                                      help=t("common.open_page")):
                    open_detail(kind, row.key)
                elif not kind:
                    st.html(f"<p class='ds-cap-title'>{row.rank}. {escape(label)}</p>")
                sub = escape(row.sublabel) if isinstance(row.sublabel, str) else ""
                st.html(f"<p style='font-size:13px;color:rgba(31,31,31,.66);margin:-6px 0 8px'>{sub}{' · ' if sub else ''}{escape(value_fmt(row))}</p>")


def ranked_table(items: pd.DataFrame, kind: str | None, key: str) -> None:
    """List view of a `stats.top()` frame; selecting a row opens the detail page."""
    view = pd.DataFrame({
        "rank": items["rank"], "image": items["image"], "label": items["label"], "sublabel": items["sublabel"],
        "plays": items["plays"], "minutes": items["minutes"].round(0),
    })
    has_image = view["image"].notna().any()
    has_sub = view["sublabel"].notna().any()
    order = ["rank"] + (["image"] if has_image else []) + ["label"] + (["sublabel"] if has_sub else []) + ["plays", "minutes"]
    event = st.dataframe(
        view, hide_index=True, column_order=order, key=key,
        on_select="rerun" if kind else "ignore", selection_mode="single-row",
        column_config={
            "rank": st.column_config.NumberColumn("#", width="small", alignment="right"),
            "image": st.column_config.ImageColumn("", width="small"),
            "label": st.column_config.TextColumn(t("common.name")),
            "sublabel": st.column_config.TextColumn(t("common.artist")),
            "plays": st.column_config.ProgressColumn(t("common.plays"), format="%d", min_value=0,
                                                     max_value=int(view["plays"].max() or 1), color="#e8558e"),
            "minutes": st.column_config.NumberColumn(t("common.minutes"), format="localized", alignment="right"),
        },
    )
    if kind:
        selected = getattr(getattr(event, "selection", None), "rows", []) or []
        if selected:
            open_detail(kind, items.iloc[selected[0]]["key"])


def value_formatter(metric: str):
    if metric == "minutes":
        return lambda row: fmt_duration(row.minutes)
    return lambda row: fmt_plays(row.plays)


def sync_status(*_args, **_kwargs) -> None:
    """The collection status now lives at the foot of the navigation rail."""


def csv_download(df: pd.DataFrame, filename: str, key: str) -> None:
    st.download_button(t("common.download_csv"), df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv", key=key, icon=":material/download:")


def excel_download(df: pd.DataFrame, filename: str, sheet: str, title: str, key: str,
                   formats: dict[str, str] | None = None) -> None:
    """Download button producing the same styled workbook as the Excel exports."""
    from app.i18n import get_lang
    from core.excel import table_sheet, to_xlsx

    st.download_button(t("common.download_excel"), to_xlsx([table_sheet(df, sheet, title, formats)], get_lang()),
                       file_name=filename, key=key, icon=":material/table_view:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def export_plays(df: pd.DataFrame) -> pd.DataFrame:
    """Plays in a flat, readable shape for CSV export."""
    return pd.DataFrame({
        "played_at_local": df["played_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "played_at_utc": df["played_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": df["track_title"], "artist": df["artist_name"], "album": df["album_title"],
        "genre": df["genre"], "listened_seconds": df["listened_seconds"].astype(int),
        "duration_is_estimated": df["duration_is_estimated"], "track_id": df["track_id"],
    })


def fmt_count(n: int) -> str:
    return fmt_int(n)
