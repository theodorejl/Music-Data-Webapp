"""Plotly charts drawn to the taste-skill app rules (references/app-screens.md §6).

One question and one hue per chart: the main data element (the current period, the
leader) in the cobalt accent, the rest in its pale tint. Straight 2px lines, no point
markers, square bars with at most a 4px top radius, 3-5 quiet horizontal gridlines,
no y-axis line, round ticks, flat x labels, a dashed reference line labelled at its end,
the event that matters annotated. Shares use 100% stacked bars of five parts at most.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.i18n import get_lang, plotly_separators, tl

# pastel-consumer tokens
ACCENT = "#1d5fd6"
ACCENT_PALE = "#b9d3f6"
CHART = ["#1d5fd6", "#b45309", "#2a8798"]  # --chart-1..3; a fourth part is the neutral "other"
CATEGORICAL = CHART
OTHER = "#cfd4da"
SEQUENTIAL = ["#eef4fd", "#dcf1ff", "#b9d3f6", "#8fb3ee", "#5f8de3", "#1d5fd6", "#164ca9", "#0a3a80"]
INK, MUTED, GRID, BASE, SURFACE = "#1b1d1f", "#5c6064", "#e5e5e5", "#c9cdd2", "#ffffff"
FONT = 'Manrope, Inter, system-ui, -apple-system, "Segoe UI", sans-serif'
CONFIG = {"displayModeBar": False, "responsive": True}


def style(fig: go.Figure, height: int = 300, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=44, r=56, t=26, b=36),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=MUTED),
        separators=plotly_separators(),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0, title=None,
                    font=dict(color=MUTED, size=13), itemwidth=30),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor="#e6e6e6", font=dict(family=FONT, color=INK, size=13)),
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=BASE, linewidth=1, ticks="", tickfont=dict(color=MUTED, size=12),
                     title=None, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=False, ticks="", nticks=5,
                     tickfont=dict(color=MUTED, size=12), title=None, automargin=True, rangemode="tozero")
    return fig


def show(fig: go.Figure, key: str | None = None) -> None:
    st.plotly_chart(fig, config=CONFIG, theme=None, key=key)


def _date_tickformat(freq: str) -> str:
    if freq == "M":
        return "%m/%Y" if get_lang() == "fr" else "%b %Y"
    return "%d/%m" if get_lang() == "fr" else "%b %d"


def _period_labels(periods: pd.Series, freq: str) -> list[str]:
    """Localized hover labels (Plotly's own month names are English only)."""
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


def _month_short(periods) -> list[str]:
    months = tl("months_short")
    return [f"{months[p.month - 1]} {p.year}" for p in pd.to_datetime(periods)]


def _time_x(fig: go.Figure, periods: pd.Series, freq: str):
    """x values for a time axis. Months use category labels: Plotly's date ticks
    drift and repeat when there are only a few monthly bars."""
    if freq == "M":
        fig.update_xaxes(type="category")
        return _month_short(periods)
    n = len(periods)
    step = 86_400_000 * (7 if freq == "W" else 1)  # one label per period when there are few of them
    if n <= 10:
        fig.update_xaxes(tickformat=_date_tickformat(freq), dtick=step, tick0=pd.Timestamp(list(periods)[0]))
    else:
        fig.update_xaxes(tickformat=_date_tickformat(freq), nticks=8)
    return periods


def _fmt(v: float) -> str:
    s = f"{v:,.0f}"
    return s.replace(",", " ") if get_lang() == "fr" else s


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _blend(c1: str, c2: str, t: float) -> str:
    a, b = _hex(c1), _hex(c2)
    return "#" + "".join(f"{round(x + (y - x) * max(0.0, min(1.0, t))):02x}" for x, y in zip(a, b))


def ramp(values, low: str = "#dcf1ff", high: str = ACCENT) -> list[str]:
    """One hue for intensity (matrices, clocks): pale for little, cobalt for a lot."""
    vals = [float(v) for v in values]
    top = max(vals) if vals else 1.0
    return [_blend(low, high, (v / top) ** 0.8 if top else 0) for v in vals]


def _reference(fig: go.Figure, value: float, label: str) -> None:
    """A 1px dashed reference line with its label at the line's end."""
    fig.add_hline(y=value, line=dict(color=MUTED, width=1, dash="dash"),
                  annotation=dict(text=label, font=dict(size=12, color=MUTED), xanchor="left", x=1.005,
                                  yanchor="middle", showarrow=False, bgcolor="rgba(0,0,0,0)"))


def bar_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 280,
                 highlight_last: bool = True) -> go.Figure:
    """Columns per period: the current period in cobalt, the others in its pale tint; the
    average as a dashed reference; the peak labelled when it stands out."""
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    xs = list(_time_x(fig, df["period"], freq))
    values = df[y].astype(float).tolist()
    colors = [ACCENT_PALE] * len(values)
    if values and highlight_last:
        colors[-1] = ACCENT
    fig.add_trace(go.Bar(
        x=xs, y=values, marker=dict(color=colors, cornerradius=4, line=dict(width=0)),
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label} %{{y:,.0f}}<extra></extra>",
    ))
    if len(values) > 2 and max(values) > 0:
        mean = sum(values) / len(values)
        _reference(fig, mean, f"{tl('chart_words')[0]} {_fmt(mean)}")
        i = values.index(max(values))
        if values[i] >= 1.6 * mean:  # annotate only a peak that stands out
            fig.add_annotation(x=xs[i], y=values[i], text=_fmt(values[i]), showarrow=False, yshift=11,
                               font=dict(size=12, color=INK))
    return fig


def line_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 280) -> go.Figure:
    """A 2px straight line with a flat 10% tint under it and its end value labelled."""
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    xs = list(_time_x(fig, df["period"], freq))
    fig.add_trace(go.Scatter(
        x=xs, y=df[y], mode="lines", line=dict(color=ACCENT, width=2, shape="linear"),
        fill="tozeroy", fillcolor="rgba(29,95,214,0.10)",
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label} %{{y:,.0f}}<extra></extra>",
    ))
    if len(df):
        fig.add_annotation(x=xs[-1], y=float(df[y].iloc[-1]), text=_fmt(float(df[y].iloc[-1])), showarrow=False,
                           xanchor="left", xshift=6, font=dict(size=12, color=INK))
    return fig


def stacked_share(df: pd.DataFrame, freq: str, other_label: str, height: int = 320) -> go.Figure:
    """100% stacked columns with 2px seams: up to three named parts and the neutral rest."""
    fig = style(go.Figure(), height, legend=True)
    labels = [c for c in df["label"].cat.categories if c in set(df["label"])]
    periods = sorted(df["period"].unique())
    x = list(_time_x(fig, pd.Series(periods), freq))
    named = [lab for lab in labels if lab != other_label][:3]
    for i, label in enumerate(named + ([other_label] if other_label in labels else [])):
        share = df[df["label"] == label].set_index("period")["share"].reindex(periods, fill_value=0.0)
        color = OTHER if label == other_label else CHART[i]
        fig.add_trace(go.Bar(
            x=x, y=share, name=str(label), marker=dict(color=color, line=dict(color=SURFACE, width=2)),
            customdata=_period_labels(pd.Series(periods), freq),
            hovertemplate=f"<b>{label}</b><br>%{{customdata}}<br>%{{y:.0%}}<extra></extra>",
        ))
    fig.update_layout(barmode="stack", bargap=0.18)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.0001], tickvals=[0, .25, .5, .75, 1])
    return fig


def bar_categories(labels: list[str], values: list[float], y_label: str, height: int = 240,
                   highlight: int | None = None) -> go.Figure:
    """Columns on a category axis (hours, weekdays); the highlighted one in cobalt."""
    fig = style(go.Figure(), height)
    vals = [float(v) for v in values]
    hi = highlight if highlight is not None else (vals.index(max(vals)) if vals else None)
    colors = [ACCENT if i == hi else ACCENT_PALE for i in range(len(vals))]
    fig.add_trace(go.Bar(x=labels, y=vals, marker=dict(color=colors, cornerradius=4),
                         hovertemplate=f"%{{x}}<br>{y_label} %{{y:,.0f}}<extra></extra>"))
    fig.update_xaxes(type="category")
    return fig


def hbar(labels: list[str], values: list[float], value_label: str, height: int | None = None,
         fmt: str = ",.0f") -> go.Figure:
    """A sorted ranking: thin rounded bars, the leader in cobalt, the value after each bar."""
    labels = [s if len(s) <= 38 else s[:37] + "…" for s in map(str, labels)][::-1]
    values = [float(v) for v in values][::-1]
    colors = [ACCENT_PALE] * len(values)
    if values:
        colors[values.index(max(values))] = ACCENT
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=colors, cornerradius=5),
        text=[f"{v:{fmt}}".replace(",", " ") if get_lang() == "fr" else f"{v:{fmt}}" for v in values],
        textposition="outside", textfont=dict(color=MUTED, size=12), cliponaxis=False,
        hovertemplate=f"%{{y}}<br>{value_label} %{{x:{fmt}}}<extra></extra>",
    ))
    style(fig, height or max(170, 34 * len(labels) + 24))
    fig.update_layout(bargap=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK, size=13), rangemode="normal")
    fig.update_layout(margin=dict(l=8 + int(6.8 * max((len(str(x)) for x in labels), default=0)), r=48, t=6, b=6))
    return fig


def heatmap_chart(matrix: pd.DataFrame, value_label: str, height: int = 300) -> go.Figure:
    """Dot matrix (weekday x hour): dot size and the one hue's depth follow the value."""
    days = tl("weekdays_short")
    xs, ys, vals = [], [], []
    for wd in matrix.index:
        for h in matrix.columns:
            xs.append(f"{h}h"); ys.append(days[wd]); vals.append(float(matrix.loc[wd, h]))
    top = max(vals) if vals and max(vals) > 0 else 1
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(size=[5 + 19 * (v / top) ** 0.7 for v in vals], color=ramp(vals, "#e7eef9", ACCENT),
                    line=dict(width=0)),
        customdata=vals, hovertemplate=f"%{{y}} %{{x}}<br>{value_label} %{{customdata:,.0f}}<extra></extra>",
    ))
    style(fig, height)
    fig.update_xaxes(type="category", showgrid=False, showline=False, tickfont=dict(size=11, color=MUTED),
                     tickvals=[f"{h}h" for h in range(0, 24, 3)])
    fig.update_yaxes(type="category", autorange="reversed", showgrid=False, categoryorder="array", categoryarray=days,
                     tickmode="array", tickvals=days, rangemode="normal")
    return fig


def polar_clock(hours: pd.Series, value_label: str, height: int = 300) -> go.Figure:
    """24-hour clock: one petal per hour in one hue, the peak hour in full cobalt."""
    vals = [float(hours.get(h, 0)) for h in range(24)]
    peak = vals.index(max(vals)) if vals and max(vals) > 0 else -1
    colors = [ACCENT if h == peak else ACCENT_PALE for h in range(24)]
    fig = go.Figure(go.Barpolar(
        r=vals, theta=[h * 15 for h in range(24)], width=[13] * 24,
        marker=dict(color=colors, line=dict(color=SURFACE, width=1.5)),
        customdata=[f"{h}h" for h in range(24)],
        hovertemplate=f"%{{customdata}}<br>{value_label} %{{r:,.0f}}<extra></extra>",
    ))
    style(fig, height)
    fig.update_layout(margin=dict(l=24, r=24, t=24, b=24), polar=dict(
        bgcolor="rgba(0,0,0,0)", hole=0.16,
        angularaxis=dict(direction="clockwise", rotation=90, tickmode="array", tickvals=[0, 90, 180, 270],
                         ticktext=["0h", "6h", "12h", "18h"], tickfont=dict(color=MUTED, size=12),
                         showline=False, gridcolor=GRID),
        radialaxis=dict(showticklabels=False, showline=False, gridcolor=GRID, ticks="")))
    return fig


def calendar(daily: pd.Series, value_label: str, height: int = 200) -> go.Figure:
    """The year as a day matrix (columns = weeks), one hue whose depth is the minutes."""
    if daily.empty:
        return style(go.Figure(), height)
    end = pd.Timestamp(daily.index.max())
    days = pd.date_range(end - pd.Timedelta(days=364), end, freq="D")
    vals = daily.reindex(days.date, fill_value=0).astype(float).tolist()
    week0 = days[0] - pd.Timedelta(days=days[0].weekday())
    xs = [int((d - week0).days // 7) for d in days]
    names = tl("weekdays_short")
    ys = [names[d.weekday()] for d in days]
    colors = ["#eef1f4" if v == 0 else c for v, c in zip(vals, ramp(vals, "#cfe0f8", "#0a3a80"))]
    labels = [f"{d.day}/{d.month}/{d.year}" if get_lang() == "fr" else f"{d.year}-{d.month:02d}-{d.day:02d}" for d in days]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers", marker=dict(size=11, symbol="square", color=colors,
                                                                           line=dict(width=0)),
                               customdata=list(zip(labels, vals)),
                               hovertemplate=f"%{{customdata[0]}}<br>{value_label} %{{customdata[1]:,.0f}}<extra></extra>"))
    style(fig, height)
    months = tl("months_short")
    ticks = [(int((d - week0).days // 7), months[d.month - 1]) for d in days if d.day == 1]
    fig.update_xaxes(tickmode="array", tickvals=[t[0] for t in ticks], ticktext=[t[1] for t in ticks], showgrid=False,
                     showline=False, zeroline=False)
    fig.update_yaxes(type="category", autorange="reversed", categoryorder="array", categoryarray=names,
                     showgrid=False, tickfont=dict(size=11, color=MUTED), rangemode="normal")
    fig.update_layout(margin=dict(l=40, r=12, t=8, b=28))
    return fig


def grouped_bars(df: pd.DataFrame, x: str, series: list[tuple[str, str]], freq: str = "M",
                 height: int = 280) -> go.Figure:
    """Two series side by side, each in its chart hue, legend in the header."""
    fig = style(go.Figure(), height, legend=True)
    labels = _period_labels(df[x], freq)
    xs = _time_x(fig, df[x], freq)
    for i, (col, label) in enumerate(series):
        fig.add_trace(go.Bar(x=xs, y=df[col], name=label, marker=dict(color=CHART[i], cornerradius=4),
                             customdata=labels, hovertemplate=f"%{{customdata}}<br>{label} %{{y}}<extra></extra>"))
    fig.update_layout(barmode="group", bargroupgap=0.1)
    return fig
