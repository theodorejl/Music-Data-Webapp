"""Universe: the generative pieces — constellation of artists, time spiral, cover orbit,
listening fingerprint — each in its own colour panel."""

from html import escape

import streamlit as st

from app.components import data, theme, ui, viz
from app.i18n import fmt_int, t, tl
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("lilac", t("rail.explore"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

k = stats.kpis(df)
lead = t("explore.hero_lead", plays=f"<b>{fmt_int(k['plays'])}</b>", artists=f"<b>{fmt_int(k['artists'])}</b>",
         genres=f"<b>{fmt_int(df['genre'].nunique())}</b>")
theme.hero("lilac", t("rail.explore"), lead, f.label, controls=data.period_control,
           art=viz.fingerprint_svg(df, "", "", size=520, framed=False))

with theme.panel("night", "constellation"):
    theme.head(t("explore.constellation_title"), t("explore.constellation_kicker"), t("explore.constellation_help"))
    viz.artist_constellation(df, {"plays": t("common.plays_short"), "artists": t("common.artists").lower(),
                                  "other": t("common.other")})

theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("sky", "spiral"):
        theme.head(t("explore.spiral_title"), t("explore.spiral_kicker"), t("explore.spiral_help"))
        viz.listening_spiral(df.head(6000), {
            "other": t("common.other"), "turn_day": t("explore.turn_day"), "turn_week": t("explore.turn_week"),
            "hours": tl("explore.hours"), "days": tl("weekdays_short"), "minutes": t("explore.dot_size"),
        })
with right:
    with theme.panel("butter", "orbit"):
        theme.head(t("explore.orbit_title"), t("explore.orbit_kicker"), t("explore.orbit_help"))
        viz.cover_orbit(stats.top(df, "album", "plays", 64), t("common.plays_short"))

theme.gap()
with theme.panel("rose", "fingerprint"):
    theme.head(t("explore.fingerprint_title"), t("explore.fingerprint_kicker"), t("explore.fingerprint_help"))
    svg = viz.fingerprint_svg(df, t("explore.fingerprint_title"), f.label)
    left, right = st.columns([1.4, 1], gap="large", vertical_alignment="center")
    with left:
        theme.html(svg)
    with right:
        st.html(f"<p class='ds-hero-lead'>{escape(t('explore.fingerprint_story'))}</p>")
        st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                           mime="image/svg+xml", icon=":material/download:", key="fp_dl", type="primary")
ui.estimated_note(df)
