"""Plotly charts sharing one visual style (pastel palette, Geist, no chrome)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.i18n import get_lang, plotly_separators, tl

# Pastel palette, order validated with the dataviz validator (light surface #FBFAF8):
# CVD ΔE ≥ 9.9, normal-vision ΔE ≥ 18.1; below 3:1 contrast -> charts carry value labels / legends.
ACCENT = "#6C7FE8"
CATEGORICAL = ["#6C7FE8", "#EE8E66", "#9B7FD9", "#3FB58E", "#D9A93A", "#E07FA8"]
OTHER = "#CFCBC3"
SEQUENTIAL = ["#F4F5FD", "#DDE2FB", "#C3CBF6", "#A4B0F1", "#8796EC", "#6C7FE8", "#5465CF", "#3F4EAE", "#2E3A88"]
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#17171A", "#4A4843", "#8A8780", "#ECEAE5", "#DAD7D0", "#FBFAF8"
FONT = 'Geist, system-ui, -apple-system, "Segoe UI", sans-serif'
CONFIG = {"displayModeBar": False, "responsive": True}


def style(fig: go.Figure, height: int = 320, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=48, r=28, t=18, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=INK_2),
        separators=plotly_separators(),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(family=FONT, color="#FFFFFF", size=12.5)),
        bargap=0.32,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickcolor=AXIS, tickfont=dict(color=MUTED), title=None,
                     automargin=True)
    fig.update_yaxes(gridcolor=GRID, griddash="dot", zeroline=False, tickfont=dict(color=MUTED), title=None,
                     automargin=True)
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
    fig.update_xaxes(tickformat=_date_tickformat(freq))
    return periods


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _blend(c1: str, c2: str, t: float) -> str:
    a, b = _hex(c1), _hex(c2)
    return "#" + "".join(f"{round(x + (y - x) * max(0.0, min(1.0, t))):02x}" for x, y in zip(a, b))


def ramp(values, low: str = "#C9D0F7", high: str = ACCENT) -> list[str]:
    """One colour per value, from a pale pastel (small) to the accent (large)."""
    vals = [float(v) for v in values]
    top = max(vals) if vals else 1.0
    return [_blend(low, high, (v / top) ** 0.8 if top else 0) for v in vals]


def _fmt(v: float) -> str:
    s = f"{v:,.0f}"
    return s.replace(",", "\u202f") if get_lang() == "fr" else s


def bar_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 300) -> go.Figure:
    """Rounded bars tinted by value, a dotted average line and the peak labelled."""
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    xs = _time_x(fig, df["period"], freq)
    values = df[y].astype(float).tolist()
    fig.add_trace(go.Bar(
        x=xs, y=values, marker=dict(color=ramp(values), cornerradius=7),
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label}: %{{y:,.0f}}<extra></extra>",
    ))
    if len(values) > 2 and max(values) > 0:
        mean = sum(values) / len(values)
        fig.add_hline(y=mean, line=dict(color=MUTED, width=1.2, dash="dot"),
                      annotation=dict(text=f"{tl('chart_words')[0]} {_fmt(mean)}", font=dict(size=11, color=MUTED),
                                      xanchor="left", x=0, yanchor="bottom", showarrow=False, bgcolor="rgba(0,0,0,0)"))
        i = values.index(max(values))
        fig.add_annotation(x=list(xs)[i], y=values[i], text=_fmt(values[i]), showarrow=False, yshift=12,
                           font=dict(size=11.5, color=INK))
    return fig


def line_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 300) -> go.Figure:
    """Smooth line with a vertical gradient fill fading into the card."""
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    xs = _time_x(fig, df["period"], freq)
    fig.add_trace(go.Scatter(
        x=xs, y=df[y], mode="lines", line=dict(color=ACCENT, width=2.6, shape="spline", smoothing=0.7),
        fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, "rgba(155,127,217,0.0)"],
                                                                      [1, "rgba(108,127,232,0.38)"]]),
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label}: %{{y:,.0f}}<extra></extra>",
    ))
    if len(df):
        fig.add_trace(go.Scatter(x=[list(xs)[-1]], y=[df[y].iloc[-1]], mode="markers+text",
                                 marker=dict(size=10, color=ACCENT, line=dict(color=SURFACE, width=3)),
                                 text=[_fmt(df[y].iloc[-1])], textposition="top left",
                                 textfont=dict(color=INK, size=12), hoverinfo="skip", cliponaxis=False))
    return fig


def stacked_share(df: pd.DataFrame, freq: str, other_label: str, height: int = 360) -> go.Figure:
    """Streamgraph-like stacked 100% areas, spline edges separated by thin surface lines."""
    fig = style(go.Figure(), height, legend=True)
    labels = [c for c in df["label"].cat.categories if c in set(df["label"])]
    periods = sorted(df["period"].unique())
    x = _time_x(fig, pd.Series(periods), freq)
    for i, label in enumerate(labels):
        share = df[df["label"] == label].set_index("period")["share"].reindex(periods, fill_value=0.0)
        color = OTHER if label == other_label else CATEGORICAL[i % len(CATEGORICAL)]
        fig.add_trace(go.Scatter(
            x=x, y=share, name=str(label), mode="lines", stackgroup="one",
            line=dict(width=1.8, color=SURFACE, shape="spline", smoothing=0.8), fillcolor=color,
            customdata=_period_labels(pd.Series(periods), freq),
            hovertemplate=f"<b>{label}</b><br>%{{customdata}}<br>%{{y:.0%}}<extra></extra>",
        ))
    fig.update_yaxes(tickformat=".0%", range=[0, 1], showgrid=False)
    return fig


def bar_categories(labels: list[str], values: list[float], y_label: str, height: int = 260) -> go.Figure:
    """Vertical bars on a category axis (e.g. hours of the day), tinted by value."""
    fig = style(go.Figure(), height)
    fig.add_trace(go.Bar(x=labels, y=values, marker=dict(color=ramp(values), cornerradius=7),
                         hovertemplate=f"%{{x}}<br>{y_label}: %{{y:,.0f}}<extra></extra>"))
    fig.update_xaxes(type="category")
    return fig


def hbar(labels: list[str], values: list[float], value_label: str, height: int | None = None,
         fmt: str = ",.0f") -> go.Figure:
    """Ranked lollipop-bars: soft track, gradient bar, value at the tip."""
    labels = [s if len(s) <= 38 else s[:37] + "…" for s in map(str, labels)][::-1]
    values = [float(v) for v in values][::-1]
    top = max(values) if values else 1
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[top] * len(values), y=labels, orientation="h", marker=dict(color="rgba(23,23,26,0.045)",
                         cornerradius=8), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=ramp(values, "#D7C8F2", ACCENT), cornerradius=8),
        text=[f"{v:{fmt}}".replace(",", "\u202f") if get_lang() == "fr" else f"{v:{fmt}}" for v in values],
        textposition="outside", textfont=dict(color=INK_2), cliponaxis=False,
        hovertemplate=f"%{{y}}<br>{value_label}: %{{x:{fmt}}}<extra></extra>",
    ))
    style(fig, height or max(180, 36 * len(labels) + 30))
    fig.update_layout(barmode="overlay", bargap=0.42)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK))
    fig.update_layout(margin=dict(l=8 + int(6.5 * max((len(str(x)) for x in labels), default=0)), r=48, t=8, b=8))
    return fig


def heatmap_chart(matrix: pd.DataFrame, value_label: str, height: int = 320) -> go.Figure:
    """Dot matrix (weekday x hour): dot size and tint follow the value."""
    days = tl("weekdays_short")
    xs, ys, vals = [], [], []
    for wd in matrix.index:
        for h in matrix.columns:
            xs.append(f"{h}h"); ys.append(days[wd]); vals.append(float(matrix.loc[wd, h]))
    top = max(vals) if vals and max(vals) > 0 else 1
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(size=[6 + 22 * (v / top) ** 0.7 for v in vals], color=ramp(vals, "#E6E3F4", ACCENT),
                    line=dict(width=0)),
        customdata=vals, hovertemplate=f"%{{y}} %{{x}}<br>{value_label}: %{{customdata:,.0f}}<extra></extra>",
    ))
    style(fig, height)
    fig.update_xaxes(type="category", showgrid=False, tickfont=dict(size=10, color=MUTED), showline=False)
    fig.update_yaxes(type="category", autorange="reversed", showgrid=False, categoryorder="array", categoryarray=days)
    return fig


def polar_clock(hours: pd.Series, value_label: str, height: int = 380) -> go.Figure:
    """24-hour clock: one petal per hour, length and tint by listening."""
    vals = [float(hours.get(h, 0)) for h in range(24)]
    fig = go.Figure(go.Barpolar(
        r=vals, theta=[h * 15 for h in range(24)], width=[13.5] * 24,
        marker=dict(color=ramp(vals, "#F2D6C8", "#9B7FD9"), line=dict(color=SURFACE, width=1.5)),
        customdata=[f"{h}h" for h in range(24)],
        hovertemplate=f"%{{customdata}}<br>{value_label}: %{{r:,.0f}}<extra></extra>",
    ))
    style(fig, height)
    fig.update_layout(polar=dict(
        bgcolor="rgba(0,0,0,0)", hole=0.18,
        angularaxis=dict(direction="clockwise", rotation=90, tickmode="array", tickvals=[0, 90, 180, 270],
                         ticktext=["0h", "6h", "12h", "18h"], tickfont=dict(color=MUTED, size=11),
                         showline=False, gridcolor=GRID),
        radialaxis=dict(showticklabels=False, showline=False, gridcolor=GRID, ticks="")))
    return fig


def calendar(daily: pd.Series, value_label: str, height: int = 210) -> go.Figure:
    """GitHub-style year: one dot per day (columns = weeks), tint by minutes."""
    if daily.empty:
        return style(go.Figure(), height)
    end = pd.Timestamp(daily.index.max())
    days = pd.date_range(end - pd.Timedelta(days=364), end, freq="D")
    vals = daily.reindex(days.date, fill_value=0).astype(float).tolist()
    week0 = days[0] - pd.Timedelta(days=days[0].weekday())
    xs = [int((d - week0).days // 7) for d in days]
    names = tl("weekdays_short")
    ys = [names[d.weekday()] for d in days]
    top = max(vals) if max(vals) > 0 else 1
    colors = ["rgba(23,23,26,0.06)" if v == 0 else c for v, c in zip(vals, ramp(vals, "#D9DEF8", "#4E5FD0"))]
    labels = [f"{d.day}/{d.month}/{d.year}" if get_lang() == "fr" else f"{d.year}-{d.month:02d}-{d.day:02d}" for d in days]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers", marker=dict(size=11, symbol="square", color=colors,
                                                                           line=dict(width=0)),
                               customdata=list(zip(labels, vals)),
                               hovertemplate=f"%{{customdata[0]}}<br>{value_label}: %{{customdata[1]:,.0f}}<extra></extra>"))
    style(fig, height)
    months = tl("months_short")
    ticks = [(int((d - week0).days // 7), months[d.month - 1]) for d in days if d.day == 1]
    fig.update_xaxes(tickmode="array", tickvals=[t[0] for t in ticks], ticktext=[t[1] for t in ticks], showgrid=False,
                     showline=False, zeroline=False)
    fig.update_yaxes(type="category", autorange="reversed", categoryorder="array", categoryarray=names,
                     showgrid=False, tickfont=dict(size=10, color=MUTED))
    fig.update_layout(margin=dict(l=40, r=12, t=8, b=28))
    return fig


def grouped_bars(df: pd.DataFrame, x: str, series: list[tuple[str, str]], freq: str = "M",
                 height: int = 300) -> go.Figure:
    """A few series side by side (series: [(column, label)])."""
    fig = style(go.Figure(), height, legend=True)
    labels = _period_labels(df[x], freq)
    xs = _time_x(fig, df[x], freq)
    for i, (col, label) in enumerate(series):
        fig.add_trace(go.Bar(x=xs, y=df[col], name=label, marker=dict(color=CATEGORICAL[i], cornerradius=6),
                             customdata=labels,
                             hovertemplate=f"%{{customdata}}<br>{label}: %{{y}}<extra></extra>"))
    fig.update_layout(barmode="group", bargroupgap=0.08)
    return fig
