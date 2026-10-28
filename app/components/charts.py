"""Plotly charts sharing one visual style (light theme, one accent color)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.i18n import get_lang, plotly_separators, tl

# Validated reference palette (light mode).
ACCENT = "#2a78d6"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#c3c2b7"
SEQUENTIAL = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
CONFIG = {"displayModeBar": False, "responsive": True}


def style(fig: go.Figure, height: int = 320, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=48, r=8, t=8, b=32),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=INK_2),
        separators=plotly_separators(),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, color=INK)),
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickcolor=AXIS, tickfont=dict(color=MUTED), title=None,
                     automargin=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED), title=None, automargin=True)
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


def bar_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 300) -> go.Figure:
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    fig.add_trace(go.Bar(
        x=_time_x(fig, df["period"], freq), y=df[y], marker=dict(color=ACCENT, cornerradius=4),
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label}: %{{y:,.0f}}<extra></extra>",
    ))
    return fig


def line_timeline(df: pd.DataFrame, y: str, freq: str, y_label: str, height: int = 300) -> go.Figure:
    labels = _period_labels(df["period"], freq)
    fig = style(go.Figure(), height)
    fig.add_trace(go.Scatter(
        x=_time_x(fig, df["period"], freq), y=df[y], mode="lines", line=dict(color=ACCENT, width=2),
        fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
        customdata=labels, hovertemplate=f"%{{customdata}}<br>{y_label}: %{{y:,.0f}}<extra></extra>",
    ))
    return fig


def stacked_share(df: pd.DataFrame, freq: str, other_label: str, height: int = 360) -> go.Figure:
    """Stacked 100% area chart from stats.share_over_time output."""
    fig = style(go.Figure(), height, legend=True)
    labels = [c for c in df["label"].cat.categories if c in set(df["label"])]
    periods = sorted(df["period"].unique())
    x = _time_x(fig, pd.Series(periods), freq)
    for i, label in enumerate(labels):
        share = df[df["label"] == label].set_index("period")["share"].reindex(periods, fill_value=0.0)
        color = OTHER if label == other_label else CATEGORICAL[i % len(CATEGORICAL)]
        fig.add_trace(go.Scatter(
            x=x, y=share, name=str(label), mode="lines", stackgroup="one",
            line=dict(width=0.5, color=SURFACE), fillcolor=color,
            customdata=_period_labels(pd.Series(periods), freq),
            hovertemplate=f"<b>{label}</b><br>%{{customdata}}<br>%{{y:.0%}}<extra></extra>",
        ))
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    return fig


def hbar(labels: list[str], values: list[float], value_label: str, height: int | None = None,
         fmt: str = ",.0f") -> go.Figure:
    """Horizontal ranked bars, biggest on top, values written at the end."""
    labels = [s if len(s) <= 38 else s[:37] + "…" for s in map(str, labels)][::-1]
    values = list(values)[::-1]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=ACCENT, cornerradius=4),
        text=[f"{v:{fmt}}".replace(",", " ") if get_lang() == "fr" else f"{v:{fmt}}" for v in values],
        textposition="outside", textfont=dict(color=INK_2), cliponaxis=False,
        hovertemplate=f"%{{y}}<br>{value_label}: %{{x:{fmt}}}<extra></extra>",
    ))
    style(fig, height or max(180, 34 * len(labels) + 30))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK))
    fig.update_layout(margin=dict(l=8 + int(6.5 * max((len(str(x)) for x in labels), default=0)), r=40, t=8, b=8))
    return fig


def heatmap_chart(matrix: pd.DataFrame, value_label: str, height: int = 300) -> go.Figure:
    days = tl("weekdays_short")
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=[f"{h}h" for h in matrix.columns], y=[days[i] for i in matrix.index],
        colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
        xgap=2, ygap=2, showscale=False,
        hovertemplate=f"%{{y}} %{{x}}<br>{value_label}: %{{z:,.0f}}<extra></extra>",
    ))
    style(fig, height)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(tickfont=dict(size=10, color=MUTED))
    return fig


def grouped_bars(df: pd.DataFrame, x: str, series: list[tuple[str, str]], freq: str = "M",
                 height: int = 300) -> go.Figure:
    """A few series side by side (series: [(column, label)])."""
    fig = style(go.Figure(), height, legend=True)
    labels = _period_labels(df[x], freq)
    xs = _time_x(fig, df[x], freq)
    for i, (col, label) in enumerate(series):
        fig.add_trace(go.Bar(x=xs, y=df[col], name=label, marker=dict(color=CATEGORICAL[i], cornerradius=4),
                             customdata=labels,
                             hovertemplate=f"%{{customdata}}<br>{label}: %{{y}}<extra></extra>"))
    fig.update_layout(barmode="group", bargroupgap=0.08)
    return fig
