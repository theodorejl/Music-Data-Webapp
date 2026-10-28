import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import t
from core import stats

f = data.get_filters()
df = data.filtered_plays()
ui.header(t("evolution.title"), f.label, lead=t("evolution.lead"), dot="mint")

if df.empty:
    ui.empty_state()
    st.stop()

c1, c2 = st.columns(2)
freq = c1.segmented_control(t("evolution.granularity"), ["D", "W", "M"], default="W", required=True,
                            format_func=lambda x: t(f"evolution.freq_{x}"), key="ev_freq")
metric = c2.segmented_control(t("tops.metric"), ["plays", "minutes"], default="minutes", required=True,
                              format_func=lambda m: t(f"common.{m}"), key="ev_metric")
label = t(f"common.{metric}")

# Per-period columns and their running total side by side, equal width, same dates (analytics pattern).
p_col, c_col = st.columns(2, gap="medium")
with p_col:
    with st.container(key="card-ev-period"):
        theme.card_head(t("evolution.per_period", metric=label), meta=f.label)
        charts.show(charts.bar_timeline(stats.timeline(df, freq), metric, freq, label, height=260), key="ev_bar")
with c_col:
    with st.container(key="card-ev-cum"):
        theme.card_head(t("evolution.cumulative"), meta=f.label)
        charts.show(charts.line_timeline(stats.cumulative(df, freq), metric, freq, label, height=260), key="ev_cum")

share_freq = "M" if freq == "M" else "W"
other = t("common.other")
left, right = st.columns(2, gap="large")
with left:
    theme.section(t("evolution.genre_share"))
    g = stats.share_over_time(df, "genre", share_freq, 3, metric, other)
    if g.empty:
        ui.empty_state(t("tops.no_genre"))
    else:
        charts.show(charts.stacked_share(g, share_freq, other), key="ev_g")
with right:
    theme.section(t("evolution.artist_share"))
    a = stats.share_over_time(df, "artist", share_freq, 3, metric, other)
    charts.show(charts.stacked_share(a, share_freq, other), key="ev_a")
st.caption(t("evolution.share_note"))
