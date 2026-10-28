"""Tiny i18n helper: t("key") looks up app/i18n/<lang>.json (dotted keys)."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import streamlit as st

LANGS = {"fr": "Français", "en": "English"}
DEFAULT_LANG = "fr"
_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load(lang: str) -> dict:
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def flatten(d: dict, prefix: str = "") -> dict[str, object]:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


@lru_cache(maxsize=None)
def _flat(lang: str) -> dict[str, object]:
    return flatten(load(lang))


def get_lang() -> str:
    return st.session_state.get("lang", DEFAULT_LANG)


def t(key: str, **kwargs) -> str:
    lang = get_lang()
    value = _flat(lang).get(key, _flat(DEFAULT_LANG).get(key, key))
    if isinstance(value, str) and kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value  # type: ignore[return-value]


def tl(key: str) -> list[str]:
    """List values (month names, weekday names)."""
    return list(_flat(get_lang()).get(key, []))


# --- formatting ----------------------------------------------------------------

def fmt_int(n) -> str:
    try:
        s = f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "–"
    return s.replace(",", " ") if get_lang() == "fr" else s


def fmt_plays(n) -> str:
    """'1 écoute' / '12 écoutes' (singular/plural)."""
    key = "common.play_short" if int(n) == 1 else "common.plays_short"
    return f"{fmt_int(n)} {t(key)}"


def fmt_num(x, decimals: int = 1) -> str:
    try:
        s = f"{float(x):,.{decimals}f}"
    except (TypeError, ValueError):
        return "–"
    if get_lang() == "fr":
        s = s.replace(",", " ").replace(".", ",")
    return s


def fmt_pct(x, decimals: int = 0) -> str:
    return fmt_num(100 * float(x), decimals) + (" %" if get_lang() == "fr" else "%")


def fmt_duration(minutes) -> str:
    """Minutes -> '12 h 05' / '12h 05m' style."""
    try:
        total = int(round(float(minutes)))
    except (TypeError, ValueError):
        return "–"
    h, m = divmod(total, 60)
    if get_lang() == "fr":
        return f"{fmt_int(h)} h {m:02d}" if h else f"{m} min"
    return f"{fmt_int(h)}h {m:02d}m" if h else f"{m} min"


def fmt_seconds(s) -> str:
    try:
        s = int(round(float(s)))
    except (TypeError, ValueError):
        return "–"
    return f"{s // 60}:{s % 60:02d}"


def fmt_date(d, with_time: bool = False, short: bool = False) -> str:
    if d is None or not hasattr(d, "year"):
        return "–"
    months = tl("months_short" if short else "months")
    if get_lang() == "fr":
        s = f"{d.day} {months[d.month - 1]} {d.year}"
    else:
        s = f"{months[d.month - 1]} {d.day}, {d.year}"
    if with_time and isinstance(d, datetime):
        s += f" {d:%H:%M}" if get_lang() == "fr" else f", {d:%H:%M}"
    return s


def fmt_month(d) -> str:
    return f"{tl('months')[d.month - 1]} {d.year}"


def fmt_datetime_short(d) -> str:
    """Compact date+time for tables: 28/10/2026 13:02 (fr) or 2026-10-28 13:02 (en)."""
    if d is None:
        return "–"
    return f"{d:%d/%m/%Y %H:%M}" if get_lang() == "fr" else f"{d:%Y-%m-%d %H:%M}"


def plotly_separators() -> str:
    """Plotly `separators`: decimal then thousands character."""
    return ", " if get_lang() == "fr" else ".,"
