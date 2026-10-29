"""Plotly charts in the "Noto" direction: vivid pastels, gradient fills, round marks, direct labels.

Colour by job (dataviz skill): categorical hues in the validated fixed order and following the
entity (a genre keeps its colour everywhere), multi-hue sequential scales that only darken
(SUNSET, LAGOON), the hour of the day on a continuous day-and-night cycle. Hues below 3:1
contrast always come with visible labels or a hover value.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components import theme
from app.i18n import get_lang, plotly_separators, tl

PALETTE = theme.PALETTE
OTHER = theme.OTHER
INK, MUTED, GRID = "#1f1f1f", "rgba(31,31,31,.62)", "rgba(31,31,31,.10)"
FONT = '"Fira Code", "JetBrains Mono", ui-monospace, Menlo, monospace'
CONFIG = {"displayModeBar": False, "responsive": True}

# multi-hue sequential scales, light to dark (lightness only goes down)
SUNSET = ["#ffe39a", "#ffbf5f", "#ff8f5e", "#f1648a", "#b85fd8", "#6a4fd8", "#3a2584"]
LAGOON = ["#f1f8cc", "#c9ef9b", "#86dac6", "#3fbfc0", "#1e9fd8", "#3f6fd0", "#3a2584"]
BLOOM = ["#ffeef4", "#ffc6dc", "#f797bd", "#e8558e", "#b8327a", "#7d1a43"]

# day-and-night cycle: deep night, dawn, sun, afternoon, sunset, dusk
_HOUR_ANCHORS = [(0, "#4b3bc0"), (4, "#8b6cf0"), (7, "#e8558e"), (10, "#f5b700"), (14, "#ff7a45"),
                 (18, "#e8558e"), (20.5, "#1e9fd8"), (24, "#4b3bc0")]


# --- basics ----------------------------------------------------------------------------------

def style(fig: go.Figure, height: int = 300, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=12, t=30, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=MUTED), separators=plotly_separators(),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    font=dict(color=INK, size=13), itemwidth=30, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(0,0,0,0)", font=dict(family=FONT, color=INK, size=13)),
        bargap=0.22, hovermode="closest",
    )
    fig.update_xaxes(showgrid=False, showline=False, zeroline=False, ticks="", tickfont=dict(color=MUTED, size=12),
                     title=None, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, griddash="dot", gridwidth=1, zeroline=False, showline=False, ticks="",
                     nticks=5, tickfont=dict(color=MUTED, size=12), title=None, automargin=True, rangemode="tozero")
    return fig


def show(fig: go.Figure, key: str | None = None) -> None:
    st.plotly_chart(fig, config=CONFIG, theme=None, key=key)


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _blend(c1: str, c2: str, t: float) -> str:
    a, b = _hex(c1), _hex(c2)
    t = max(0.0, min(1.0, t))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def rgba(c: str, alpha: float) -> str:
    r, g, b = _hex(c)
    return f"rgba({r},{g},{b},{alpha})"


def scale_color(scale: list[str], t: float) -> str:
    t = max(0.0, min(1.0, t))
    pos = t * (len(scale) - 1)
    i = min(int(pos), len(scale) - 2)
    return _blend(scale[i], scale[i + 1], pos - i)


def scale_colors(values, scale: list[str] = SUNSET, low: float = 0.12) -> list[str]:
    vals = [float(v) for v in values]
    top = max(vals) if vals else 1.0
    return [scale_color(scale, low + (1 - low) * ((v / top) ** 0.85 if top else 0)) for v in vals]


def hour_color(h: float) -> str:
    h = h % 24
    for (h0, c0), (h1, c1) in zip(_HOUR_ANCHORS, _HOUR_ANCHORS[1:]):
        if h0 <= h <= h1:
            return _blend(c0, c1, (h - h0) / (h1 - h0))
    return _HOUR_ANCHORS[0][1]


def category_colors(labels, other_label: str | None = None) -> dict[str, str]:
    """Genres keep one colour everywhere (by their rank over the whole history); anything else
    gets the palette in order of appearance. "Other" is grey."""
    from app.components import data

    order = data.genre_order()
    out: dict[str, str] = {}
    used: set[str] = set()
    for lab in labels:
        if lab == other_label:
            out[lab] = OTHER
        elif lab in order and order.index(lab) < len(PALETTE):
            out[lab] = PALETTE[order.index(lab)]
            used.add(out[lab])
    free = [c for c in PALETTE if c not in used]
    for lab in labels:
        if lab not in out:
            out[lab] = free.pop(0) if free else OTHER
    return out


def _fmt(v: float) -> str:
    s = f"{v:,.0f}"
    return s.replace(",", " ") if get_lang() == "fr" else s


def _period_labels(periods, freq: str) -> list[str]:
    months = tl("months")
    out = []
    for p in pd.to_datetime(periods):
        if freq == "M":
            out.append(f"{months[p.month - 1]} {p.year}")
        elif get_lang() == "fr":
            out.append(f"{p.day} {months[p.month - 1]} {p.year}")
        else:
            out.append(f"{months[p.month - 1]} {p.day}, {p.year}")
    return out


def _short_labels(periods, freq: str) -> list[str]:
    months = tl("months_short")
    out = []
    for p in pd.to_datetime(periods):
        if freq == "M":
            out.append(f"{months[p.month - 1]} {str(p.year)[2:]}")
        else:
            out.append(f"{p.day} {months[p.month - 1]}" if get_lang() == "fr" else f"{months[p.month - 1]} {p.day}")
    return out


def _category_x(fig: go.Figure, labels: list[str]) -> None:
    step = max(1, math.ceil(len(labels) / 9))
    fig.update_xaxes(type="category", tickmode="array", tickvals=labels[::step], ticktext=labels[::step])


def _covers_on(fig: go.Figure, points: list[tuple[float, float, str]], sizex: float, sizey: float,
               yanchor: str = "middle") -> None:
    """Album covers / artist photos placed on the chart in data units: (x, y, url)."""
    for x, y, url in points:
        if isinstance(url, str) and url:
            fig.add_layout_image(source=url, xref="x", yref="y", x=x, y=y, sizex=sizex, sizey=sizey,
                                 xanchor="center", yanchor=yanchor, sizing="contain", layer="above")


def _hours_minutes(v: float) -> str:
    v = float(v)
    if v >= 60:
        return f"{int(v // 60)} h {int(v % 60):02d}"
    return f"{int(round(v))} min"


def _value_text(v: float, unit: str) -> str:
    return _hours_minutes(v) if unit == "minutes" else _fmt(v)


# --- time ----------------------------------------------------------------------------------

def flow(df: pd.DataFrame, y: str, freq: str, y_label: str, family: str = "sky", height: int = 280,
         avg_label: str | None = None, peak_label: str | None = None, covers: dict | None = None) -> go.Figure:
    """Smooth area with a vertical gradient fill, the average dotted, and its peak marked with the
    cover of what played most then (covers: {period: (url, title, artist)})."""
    c, deep = theme.mid(family), theme.ink(family)
    labels = _short_labels(df["period"], freq)
    hover = _period_labels(df["period"], freq)
    vals = df[y].astype(float).tolist()
    unit = "" if y == "minutes" else y_label
    fig = go.Figure(go.Scatter(
        x=labels, y=vals, mode="lines", line=dict(color=deep, width=3, shape="spline", smoothing=0.8),
        fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, rgba(c, 0.02)], [0.6, rgba(c, 0.35)], [1, rgba(c, 0.8)]]),
        customdata=[[h, _value_text(v, y)] for h, v in zip(hover, vals)],
        hovertemplate=f"%{{customdata[0]}}<br><b>%{{customdata[1]}}</b> {unit}<extra></extra>"))
    if vals and max(vals) > 0:
        i = max(range(len(vals)), key=vals.__getitem__)
        fig.add_trace(go.Scatter(x=[labels[i]], y=[vals[i]], mode="markers", hoverinfo="skip",
                                 marker=dict(size=16, color="#ffffff", line=dict(color=deep, width=4))))
        peak_cover = (covers or {}).get(df["period"].iloc[i], (None,))[0]
        top = max(vals)
        text = f"<b>{_value_text(vals[i], y)}</b>" + (f" {peak_label}" if peak_label else "")
        if isinstance(peak_cover, str) and peak_cover:  # the record wears the cover of what played most then
            _covers_on(fig, [(i, top * 1.08, peak_cover)], sizex=max(0.8, len(vals) * 0.09), sizey=top * 0.3, yanchor="bottom")
            fig.add_annotation(x=i, y=top * 1.4, text=text, showarrow=False, yanchor="bottom", font=dict(color=deep, size=13))
        else:
            fig.add_annotation(x=i, y=vals[i], text=text.replace(" ", "<br>", 1) if peak_label else text,
                               showarrow=False, yshift=30, font=dict(color=deep, size=13))
        if avg_label and len(vals) > 2:
            avg = sum(vals) / len(vals)
            fig.add_hline(y=avg, line=dict(color=rgba(deep, 0.55), width=1.5, dash="dot"),
                          annotation=dict(text=f"{avg_label} {_value_text(avg, y)}", font=dict(size=12, color=deep),
                                          xanchor="right", x=1, yanchor="bottom", showarrow=False))
    style(fig, height, legend=False)
    _category_x(fig, labels)
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, max(vals + [1]) * (1.62 if covers else 1.35)])
    return fig


def bar_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 280,
                 highlight_last: bool = True, scale: list[str] | None = None, covers: dict | None = None) -> go.Figure:
    """Rounded columns coloured along a multi-hue scale by their own value (taller = deeper);
    with up to 16 columns, each wears the cover of what played most in it."""
    labels = _short_labels(df["period"], freq)
    vals = df[y].astype(float).tolist()
    colors = scale_colors(vals, scale or SUNSET)
    text = [_value_text(v, y) if v and len(vals) <= 14 else "" for v in vals]
    unit = "" if y == "minutes" else y_label
    fig = go.Figure(go.Bar(
        x=labels, y=vals, marker=dict(color=colors, cornerradius=10, line=dict(width=0)),
        text=text, textposition="outside", textfont=dict(size=12, color=INK), cliponaxis=False,
        customdata=[[h, _value_text(v, y)] for h, v in zip(_period_labels(df["period"], freq), vals)],
        hovertemplate=f"%{{customdata[0]}}<br><b>%{{customdata[1]}}</b> {unit}<extra></extra>"))
    style(fig, height)
    _category_x(fig, labels)
    top = max(vals + [1])
    if covers and len(vals) <= 16:
        _covers_on(fig, [(i, v + top * 0.13, covers.get(p, (None,))[0]) for i, (p, v) in enumerate(zip(df["period"], vals)) if v],
                   sizex=0.8, sizey=top * 0.2, yanchor="bottom")
        fig.update_traces(textposition="inside", insidetextanchor="end", textfont=dict(color="#ffffff", size=11))
        fig.update_yaxes(range=[0, top * 1.42])
    else:
        fig.update_yaxes(range=[0, top * 1.2])
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return fig


def line_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 280) -> go.Figure:
    return flow(df, y, freq, y_label, "lilac", height)


def stream(share: pd.DataFrame, freq: str, other_label: str, height: int = 360, normalized: bool = False) -> go.Figure:
    """Stacked smooth bands (genres or artists over time), each in its own colour."""
    labels = list(share["label"].cat.categories) if hasattr(share["label"], "cat") else list(dict.fromkeys(share["label"]))
    labels = [lab for lab in labels if (share["label"] == lab).any()]
    colors = category_colors(labels, other_label)
    periods = sorted(share["period"].unique())
    x = _short_labels(periods, freq)
    hover = _period_labels(periods, freq)
    fig = go.Figure()
    for lab in labels:
        d = share[share["label"] == lab].groupby("period")[["share", "value"]].sum().reindex(periods)
        vals = (d["share"] * 100 if normalized else d["value"]).fillna(0).astype(float).tolist()
        shown = [f"{v:.0f} %" if normalized else _fmt(v) for v in vals]
        fig.add_trace(go.Scatter(
            x=x, y=vals, name=str(lab), mode="lines", stackgroup="one",
            line=dict(width=1.5, color="#ffffff", shape="spline", smoothing=0.7),
            fillcolor=rgba(colors[lab], 0.9 if lab != other_label else 0.55),
            customdata=[[h, s] for h, s in zip(hover, shown)],
            hovertemplate=f"<b>{lab}</b><br>%{{customdata[0]}}: %{{customdata[1]}}<extra></extra>"))
    style(fig, height, legend=True)
    _category_x(fig, x)
    fig.update_yaxes(showticklabels=normalized, ticksuffix=" %" if normalized else "",
                     range=[0, 100] if normalized else None, showgrid=False)
    return fig


def stacked_share(df: pd.DataFrame, freq: str, other_label: str, height: int = 340) -> go.Figure:
    return stream(df, freq, other_label, height, normalized=True)


def bump(ranks: pd.DataFrame, freq: str, height: int = 400) -> go.Figure:
    """Rank of each leader per period (1 at the top): one coloured line each, and at every point
    the artist's photo or the album cover, so you see who climbs and who falls."""
    names = list(dict.fromkeys(ranks.sort_values(["period", "rank"], ascending=[False, True])["label"]))
    colors = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(names)}
    periods = sorted(ranks["period"].unique())
    x = _short_labels(periods, freq)
    hover = _period_labels(periods, freq)
    fig = go.Figure()
    max_rank = int(ranks["rank"].max()) if not ranks.empty else 5
    images = []
    for n in names:
        d = ranks[ranks["label"] == n].groupby("period").first().reindex(periods)
        ys = d["rank"].tolist()
        img = next((u for u in d["image"] if isinstance(u, str) and u), None) if "image" in d else None
        fig.add_trace(go.Scatter(
            x=list(range(len(x))), y=ys, mode="lines+markers", name=n, connectgaps=False,
            line=dict(color=colors[n], width=5, shape="spline", smoothing=0.6),
            marker=dict(size=34 if img else 24, color=colors[n], line=dict(color="#ffffff", width=2)),
            customdata=hover, hovertemplate=f"<b>{n}</b><br>%{{customdata}} : n° %{{y}}<extra></extra>"))
        if img:
            images += [(i, v, img) for i, v in enumerate(ys) if v == v]
        last = [(i, v) for i, v in enumerate(ys) if v == v]
        if last:
            i, v = last[-1]
            fig.add_annotation(x=i, y=v, text=f"<b>{n}</b>", showarrow=False, xanchor="left", xshift=24,
                               font=dict(color=INK, size=13))
    _covers_on(fig, images, sizex=0.62, sizey=0.62)
    style(fig, height)
    step = 2 if len(x) > 6 else 1
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, len(x), step)), ticktext=x[::step], showgrid=True,
                     gridcolor=GRID, griddash="dot", tickangle=0, range=[-0.5, len(x) - 0.5])
    fig.update_yaxes(autorange=False, range=[max_rank + 0.7, 0.3], showgrid=False, showticklabels=False, rangemode=None)
    fig.update_layout(margin=dict(l=8, r=170, t=20, b=8))
    return fig


# --- shapes ----------------------------------------------------------------------------------

def bars(labels: list[str], values: list[float], unit: str = "", height: int = 260,
         colors: list[str] | None = None, scale: list[str] = SUNSET, covers: list | None = None) -> go.Figure:
    """Vertical rounded columns, coloured per item (given colours or along a scale), values on top,
    and, when given, a cover above each column (covers: one url per column)."""
    vals = [float(v) for v in values]
    cols = colors or scale_colors(vals, scale)
    shown = [_value_text(v, unit) if v else "" for v in vals]
    fig = go.Figure(go.Bar(
        x=list(labels), y=vals, marker=dict(color=cols, cornerradius=12),
        text=shown, textposition="outside", textfont=dict(size=12, color=INK), cliponaxis=False,
        customdata=shown, hovertemplate="%{x}: <b>%{customdata}</b><extra></extra>"))
    style(fig, height)
    fig.update_xaxes(type="category", tickfont=dict(color=INK, size=12))
    top = max(vals + [1])
    if covers and len(vals) <= 24:
        _covers_on(fig, [(i, v + top * 0.13, c) for i, (v, c) in enumerate(zip(vals, covers)) if v],
                   sizex=0.85, sizey=top * 0.2, yanchor="bottom")
        fig.update_traces(textposition="inside", insidetextanchor="end", textfont=dict(color="#ffffff", size=11))
        fig.update_yaxes(range=[0, top * 1.42])
    else:
        fig.update_yaxes(range=[0, top * 1.22])
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return fig


def bar_categories(labels: list[str], values: list[float], y_label: str, height: int = 240,
                   highlight: int | None = None) -> go.Figure:
    return bars(labels, values, "minutes" if "min" in y_label.lower() else "", height)


def hbar(labels: list[str], values: list[float], value_label: str, height: int | None = None,
         colors: list[str] | None = None, scale: list[str] = LAGOON) -> go.Figure:
    """Horizontal rounded bars, biggest on top, each its own colour, value after the bar."""
    labels, vals = [str(x) for x in labels], [float(v) for v in values]
    cols = colors or scale_colors(vals, scale, low=0.3)
    fig = go.Figure(go.Bar(
        y=labels, x=vals, orientation="h", marker=dict(color=cols, cornerradius=10),
        text=[_fmt(v) for v in vals], textposition="outside", textfont=dict(size=12, color=INK), cliponaxis=False,
        hovertemplate=f"%{{y}}: <b>%{{x:,.0f}}</b> {value_label}<extra></extra>"))
    style(fig, height or max(220, 34 * len(labels) + 40))
    fig.update_yaxes(autorange="reversed", showgrid=False, type="category", tickfont=dict(color=INK, size=13), rangemode=None,
                     tickmode="array", tickvals=labels, ticktext=[x if len(x) <= 26 else x[:25] + "…" for x in labels])
    fig.update_xaxes(showticklabels=False, range=[0, max(vals + [1]) * 1.18])
    fig.update_layout(bargap=0.32)
    return fig


def donut(labels: list[str], values: list[float], center: str, center_sub: str = "", height: int = 320,
          other_label: str | None = None) -> go.Figure:
    cmap = category_colors(labels, other_label)
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.64, sort=False, direction="clockwise",
        marker=dict(colors=[cmap[lab] for lab in labels], line=dict(color="#ffffff", width=3)),
        textinfo="percent", textposition="outside", textfont=dict(size=12, color=INK),
        hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>"))
    fig.add_annotation(text=f"<span style='font-size:30px'>{center}</span><br><span style='font-size:12px'>{center_sub}</span>",
                       showarrow=False, font=dict(color=INK, family=FONT))
    style(fig, height, legend=False)
    fig.update_layout(margin=dict(l=30, r=30, t=30, b=30))
    return fig


# --- habits ----------------------------------------------------------------------------------

def radial_clock(by_hour: pd.Series, unit: str, height: int = 380) -> go.Figure:
    """24 petals around a clock, each coloured by its moment of the day (night indigo, dawn rose,
    sun yellow, afternoon coral, dusk sky)."""
    values = by_hour.reindex(range(24), fill_value=0).astype(float)
    fig = go.Figure(go.Barpolar(
        r=values.tolist(), theta=[h * 15 + 7.5 for h in range(24)], width=[13.2] * 24,
        marker=dict(color=[hour_color(h + 0.5) for h in range(24)], line=dict(color="#ffffff", width=1.5)),
        customdata=[[f"{h} h – {h + 1} h", _value_text(v, unit)] for h, v in enumerate(values)],
        hovertemplate="%{customdata[0]}<br><b>%{customdata[1]}</b><extra></extra>"))
    style(fig, height)
    fig.update_layout(
        margin=dict(l=36, r=36, t=30, b=30),
        polar=dict(bgcolor="rgba(255,255,255,.35)", hole=0.28,
                   radialaxis=dict(showticklabels=False, showline=False, ticks="", gridcolor="rgba(31,31,31,.08)"),
                   angularaxis=dict(direction="clockwise", rotation=90, tickmode="array",
                                    tickvals=[0, 90, 180, 270], ticktext=["0 h", "6 h", "12 h", "18 h"],
                                    tickfont=dict(size=13, color=INK), showline=False, gridcolor="rgba(31,31,31,.08)")))
    return fig


def polar_clock(hours: pd.Series, value_label: str, height: int = 300) -> go.Figure:
    return radial_clock(hours, "minutes" if "min" in value_label.lower() else "", height)


def dot_matrix(matrix: pd.DataFrame, value_label: str, height: int = 340) -> go.Figure:
    """Weekday × hour as a grid of dots: size is the amount, colour the moment of the day."""
    days = tl("weekdays_short")
    xs, ys, sizes, colors, text = [], [], [], [], []
    top = float(matrix.values.max()) or 1.0
    for wd in range(7):
        for h in range(24):
            v = float(matrix.loc[wd, h])
            xs.append(h); ys.append(days[wd])
            sizes.append(5 + 25 * math.sqrt(v / top) if v else 4)
            colors.append(hour_color(h + 0.5) if v else "rgba(31,31,31,.12)")
            text.append(f"{days[wd]} {h} h : {_fmt(v)} {value_label}")
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers", marker=dict(size=sizes, color=colors, line=dict(width=0)),
                               text=text, hovertemplate="%{text}<extra></extra>"))
    style(fig, height)
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, 24, 3)), ticktext=[f"{h} h" for h in range(0, 24, 3)],
                     range=[-0.7, 23.7])
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(reversed(days)), showgrid=False,
                     tickfont=dict(color=INK, size=13), rangemode=None)
    return fig


def heatmap_chart(matrix: pd.DataFrame, value_label: str, height: int = 320) -> go.Figure:
    return dot_matrix(matrix, value_label, height)


def ridgeline(df: pd.DataFrame, height: int = 430) -> go.Figure:
    """One smooth hour-of-day profile per weekday, stacked like hills, each in its colour."""
    days = tl("weekdays")
    hours = list(range(24))
    profiles = []
    for wd in range(7):
        d = df[df["played_local"].dt.weekday == wd]
        prof = d.groupby(d["played_local"].dt.hour)["minutes"].sum().reindex(hours, fill_value=0).astype(float)
        profiles.append([(prof[(h - 1) % 24] + 2 * prof[h] + prof[(h + 1) % 24]) / 4 for h in hours])
    top = max((max(p) for p in profiles), default=1) or 1
    fig = go.Figure()
    for wd in range(7):
        base = (6 - wd) * 0.62
        color = PALETTE[wd % len(PALETTE)]
        fig.add_trace(go.Scatter(x=hours, y=[base] * 24, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=hours, y=[base + 1.3 * v / top for v in profiles[wd]], mode="lines", fill="tonexty",
            line=dict(color=_blend(color, "#1f1f1f", 0.3), width=2, shape="spline"),
            fillcolor=rgba(color, 0.8), showlegend=False,
            customdata=[_hours_minutes(v) for v in profiles[wd]],
            hovertemplate=f"<b>{days[wd]}</b> %{{x}} h : %{{customdata}}<extra></extra>"))
    style(fig, height)
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, 24, 3)), ticktext=[f"{h} h" for h in range(0, 24, 3)], range=[0, 23])
    fig.update_yaxes(tickmode="array", tickvals=[(6 - wd) * 0.62 + 0.12 for wd in range(7)], ticktext=days,
                     showgrid=False, tickfont=dict(color=INK, size=13), rangemode=None, range=[-0.1, 6 * 0.62 + 1.5])
    return fig


def calendar(daily: pd.Series, value_label: str, height: int = 230, scale: list[str] = LAGOON) -> go.Figure:
    """The last 53 weeks as rounded day cells on a lime → teal → sky → indigo scale."""
    if daily.empty:
        return style(go.Figure(), height)
    s = pd.Series(daily)
    s.index = pd.to_datetime(s.index)
    end = s.index.max().normalize()
    start = end - pd.Timedelta(days=7 * 53 - 1)
    start -= pd.Timedelta(days=start.weekday())
    days = pd.date_range(start, end, freq="D")
    s = s.groupby(level=0).sum().reindex(days, fill_value=0)
    week = [(d - start).days // 7 for d in days]
    top = float(s.max()) or 1.0
    colors = ["rgba(31,31,31,.07)" if v == 0 else scale_color(scale, 0.15 + 0.85 * (v / top) ** 0.7) for v in s]
    wd = tl("weekdays_short")
    fig = go.Figure(go.Scatter(
        x=week, y=[d.weekday() for d in days], mode="markers",
        marker=dict(symbol="square", size=13, color=colors, line=dict(width=0)),
        customdata=[[f"{d.day:02d}/{d.month:02d}/{d.year}", _hours_minutes(v)] for d, v in zip(days, s)],
        hovertemplate="%{customdata[0]} : <b>%{customdata[1]}</b><extra></extra>"))
    months = tl("months_short")
    firsts = [(i, d) for i, d in zip(week, days) if d.day <= 7 and d.weekday() == 0]
    style(fig, height)
    fig.update_xaxes(tickmode="array", tickvals=[i for i, _ in firsts], ticktext=[months[d.month - 1] for _, d in firsts],
                     range=[-1, max(week) + 1], tickfont=dict(color=INK, size=12))
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=[0, 2, 4, 6], ticktext=[wd[0], wd[2], wd[4], wd[6]],
                     showgrid=False, rangemode=None, tickfont=dict(color=INK, size=12))
    return fig


# --- discoveries -------------------------------------------------------------------------------

def beeswarm(firsts: pd.DataFrame, unit_label: str, height: int = 360, other_label: str | None = None) -> go.Figure:
    """Each discovery a dot on the date of its first play, sized by plays since, coloured by genre.
    firsts columns: label, first_played, plays, genre."""
    d = firsts.copy()
    d["day"] = pd.to_datetime(d["first_played"]).dt.tz_localize(None).dt.normalize()
    d = d.sort_values(["day", "plays"], ascending=[True, False])
    week = d["day"].dt.to_period("W")
    d["slot"] = d.groupby(week).cumcount()
    d["y"] = d["slot"].map(lambda k: ((k + 1) // 2) * (1 if k % 2 else -1))
    genres = d["genre"].fillna(other_label or "–")
    cmap = category_colors(list(genres.value_counts().index), other_label)
    fig = go.Figure(go.Scatter(
        x=d["day"], y=d["y"], mode="markers",
        marker=dict(size=(9 + 4.5 * d["plays"].clip(upper=80) ** 0.5).tolist(), color=[cmap[g] for g in genres],
                    line=dict(color="#ffffff", width=1.5), opacity=0.95),
        customdata=list(zip(d["label"], genres, d["plays"])),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]} " + unit_label + "<extra></extra>"))
    style(fig, height)
    fig.update_yaxes(visible=False, rangemode=None)
    short = (d["day"].max() - d["day"].min()).days < 62 if not d.empty else True
    fig.update_xaxes(showgrid=True, gridcolor=GRID, griddash="dot", tickfont=dict(color=INK),
                     tickformat=("%d/%m" if short else "%m/%Y") if get_lang() == "fr" else ("%b %d" if short else "%b %Y"))
    return fig


def grouped_bars(df: pd.DataFrame, x: str, series: list[tuple[str, str]], freq: str = "M",
                 height: int = 300) -> go.Figure:
    labels = _short_labels(df[x], freq)
    fig = go.Figure()
    families = ["rose", "sky", "butter", "lime"]
    for i, (col, name) in enumerate(series):
        fig.add_trace(go.Bar(x=labels, y=df[col], name=name, marker=dict(color=theme.mid(families[i % 4]), cornerradius=8),
                             hovertemplate=f"{name} : <b>%{{y}}</b><extra></extra>"))
    style(fig, height, legend=True)
    _category_x(fig, labels)
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    return fig


def cumulative_lines(per_month: pd.DataFrame, cols: list[tuple[str, str, str]], height: int = 300) -> go.Figure:
    """Running totals (e.g. new artists / albums) as gradient-filled curves. cols: (column, name, family)."""
    labels = _short_labels(per_month["period"], "M")
    fig = go.Figure()
    for col, name, family in cols:
        c = theme.mid(family)
        fig.add_trace(go.Scatter(
            x=labels, y=per_month[col].cumsum(), name=name, mode="lines" if len(labels) > 1 else "markers",
            marker=dict(size=14, color=theme.ink(family)),
            line=dict(color=theme.ink(family), width=3, shape="spline"),
            fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, rgba(c, 0.02)], [1, rgba(c, 0.6)]]),
            hovertemplate=f"{name} : <b>%{{y}}</b><extra></extra>"))
    style(fig, height, legend=True)
    _category_x(fig, labels)
    return fig
