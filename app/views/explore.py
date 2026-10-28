"""Original visualisations: time spiral, cover orbit, artist constellation, fingerprint."""

import streamlit as st

from app.components import data, theme, ui, viz
from app.i18n import t, tl
from core import stats

f = data.get_filters()
df = data.filtered_plays()
theme.page_header(t("explore.title"), kicker=f.label, lead=t("explore.lead"), dot="lavender")

if df.empty:
    ui.empty_state()
    st.stop()

theme.section(t("explore.spiral_title"), t("explore.spiral_kicker"))
st.caption(t("explore.spiral_help"))
viz.listening_spiral(df.head(6000), {
    "other": t("common.other"), "turn_day": t("explore.turn_day"), "turn_week": t("explore.turn_week"),
    "hours": tl("explore.hours"), "days": tl("weekdays_short"), "minutes": t("explore.dot_size"),
})

theme.section(t("explore.orbit_title"), t("explore.orbit_kicker"))
st.caption(t("explore.orbit_help"))
viz.cover_orbit(stats.top(df, "album", "plays", 64), t("common.plays_short"))

theme.section(t("explore.constellation_title"), t("explore.constellation_kicker"))
st.caption(t("explore.constellation_help"))
viz.artist_constellation(df, t("common.plays_short"), t("common.other"))

theme.section(t("explore.fingerprint_title"), t("explore.fingerprint_kicker"))
st.caption(t("explore.fingerprint_help"))
svg = viz.fingerprint_svg(df, t("explore.fingerprint_title"), f.label)
st.markdown(svg, unsafe_allow_html=True)
st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                   mime="image/svg+xml", icon=":material/download:", key="fp_dl")
