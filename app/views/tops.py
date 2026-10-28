import streamlit as st

from app.components import charts, data, ui
from app.i18n import t
from core import stats

f = data.get_filters()
df = data.filtered_plays()
ui.header(t("tops.title"), f.label)

if df.empty:
    ui.empty_state()
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
metric = c1.segmented_control(t("tops.metric"), ["plays", "minutes"], default="plays", required=True,
                              format_func=lambda m: t(f"common.{m}"), key="tops_metric")
view = c2.segmented_control(t("tops.view"), ["grid", "list"], default="grid", required=True,
                            format_func=lambda v: t(f"tops.view_{v}"), key="tops_view")
n = c3.selectbox(t("tops.count"), [10, 20, 50, 100, 0], key="tops_n",
                 format_func=lambda x: t("tops.count_all") if x == 0 else str(x))

tabs = st.tabs([t("common.artists"), t("common.albums"), t("common.tracks"), t("common.genres")])
for tab, dim in zip(tabs, stats.DIMENSIONS):
    with tab:
        items = stats.top(df, dim, metric, n or len(df))
        if items.empty:
            ui.empty_state(t("tops.no_genre") if dim == "genre" else None)
            continue
        kind = None if dim == "genre" else dim
        if dim == "genre":
            values = items["minutes"].round(0) if metric == "minutes" else items["plays"]
            charts.show(charts.hbar(items["label"], values, t(f"common.{metric}")), key=f"top_g_{metric}")
            unknown = int(df["genre"].isna().sum())
            if unknown:
                st.caption(t("tops.unknown_genre", n=unknown))
        elif view == "grid" and len(items) <= 100:
            ui.cover_grid(items, kind, ui.value_formatter(metric), columns=5, key=f"tg_{dim}")
        else:
            ui.ranked_table(items, kind, key=f"tl_{dim}_{metric}_{n}")
        export = items.drop(columns=["image"]).rename(columns={"key": "id"})
        ui.csv_download(export, f"top_{dim}_{metric}.csv", key=f"dl_{dim}")
ui.estimated_note(df)
