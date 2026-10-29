"""From Insta: type an Instagram account, get the playlist of the music it posts.

The studio explains where the music is found (captions, comments, the sound of videos) and what
is ready, takes the account (typed, pasted as a link, or picked among the accounts already read),
the number of tracks to extract (with the expected time) and runs the extraction under the loading
bar. Each account's playlist is kept until it is extracted again, which then reads only the new
posts. See core/instamusic.py.
"""

import threading
import time
from html import escape

import pandas as pd
import streamlit as st

from app.components import data, interactive, studio, theme, ui
from app.i18n import fmt_int, t
from core import instamusic as im

SOURCES = ("caption", "comment", "audio")
FATAL = ("setup", "token", "account", "not_found", "rate", "network", "invalid")
ready = im.configured()
now = pd.Timestamp.now(tz=data.timezone_name())
known = im.accounts()


def ago(iso: str) -> str:
    minutes = max(0, int((now - pd.Timestamp(iso)).total_seconds() // 60))
    if minutes < 1:
        return t("reco.ago_now")
    if minutes < 60:
        return t("reco.ago_min", n=minutes)
    if minutes < 48 * 60:
        return t("reco.ago_h", n=minutes // 60)
    return t("reco.ago_d", n=minutes // 1440)


def _picked() -> None:
    if st.session_state.get("ig_pick"):
        st.session_state["ig_input"] = "@" + st.session_state["ig_pick"]


def extract(account: str, n: int, audio: bool, slot) -> None:
    """Run the extraction in a worker thread and redraw the loading bar until it is done."""
    state = im.load(account)
    plan = im.estimate(n, state, (state.get("profile") or {}).get("media_count"), audio)
    progress = im.Progress(plan["posts"], n)
    box: dict = {}

    def work():
        try:
            box["state"] = im.run(account, n, recognizer=im.AuddRecognizer() if audio else None, progress=progress,
                                  audio=audio, state=state)
        except Exception as exc:  # shown below instead of crashing the page
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    steps = {k: t(f"insta.step_{k}") for k in ("profile", "posts", "text", "audio", "memory")}
    labels = {"eta": t("reco.eta"), "eta_wait": t("reco.eta_wait"), "done": t("reco.eta_done"),
              "found": t("insta.found"), "calls": t("insta.posts_read")}
    while worker.is_alive():
        frac, el = progress.fraction, progress.elapsed
        eta = max(0.0, plan["seconds"] - el) if frac < 0.2 else el * (1 - frac) / max(frac, 1e-3)
        step = steps.get(progress.step, "").format(account=account, date=progress.detail or "…")
        slot.html(studio.progress_html("insta", frac, el, eta, step, progress.found, n, progress.posts_done,
                                       progress.posts_planned, labels))
        time.sleep(0.12)
    worker.join()
    result = box.get("state")
    if result is None:
        slot.error(t("insta.failed"))
        return
    if result.get("profile"):
        im.save(result)
    st.session_state["ig_account"] = account
    st.session_state["ig_notice"] = result.get("error")
    if result.get("error") in FATAL and not result.get("tracks"):
        slot.error(t(f"insta.error_{result['error']}", account=account))
        return
    found = len(im.playlist(result))
    slot.html(studio.progress_html("insta", 1.0, progress.elapsed, 0, t("insta.step_done", n=fmt_int(found)), found, n,
                                   progress.posts_done, progress.posts_planned, labels, done=True))
    time.sleep(0.6)
    st.rerun()


# --- the studio: where music is found, the account, how many tracks, extract -----------------------------
current = st.session_state.get("ig_account") or (known[0]["username"] if known else None)
if st.session_state.pop("ig_reset", False):  # an account was just forgotten
    st.session_state["ig_input"] = ""
st.session_state.setdefault("ig_input", f"@{current}" if current else "")
color = studio.MODE_COLORS["insta"][0]

with st.container(key="hero-rose-insta"):
    st.html(f"<div class='ds-kicker'><i></i>{escape(t('insta.kicker'))}</div>"
            f"<h1 class='ds-hero-title'>{escape(t('rail.insta'))}</h1>"
            f"<p class='ds-hero-lead' style='max-width:84ch'>{escape(t('insta.lead'))}</p>")
    states = {"caption": "on", "comment": "off", "audio": "on" if ready["audio"] else "todo"}
    cols = st.columns(3, gap="medium")
    for col, source in zip(cols, SOURCES):
        with col, st.container(key=f"mode-src-{source}"):
            theme.html(studio.source_card(source, t(f"insta.src_{source}"), t(f"insta.src_{source}_tag"),
                                          t(f"insta.src_{source}_how"), t(f"insta.src_{states[source]}_{source}"),
                                          states[source]))
    st.html(f"<style>.st-key-hero-rose-insta{{--mc:{color}}}"
            ".st-key-mode-src-comment{opacity:.72}</style>")

    theme.gap()
    left, mid, right = st.columns([2.2, 1, 1.2], gap="large", vertical_alignment="center")
    with left:
        st.html(f"<div class='rs-label'>{escape(t('insta.account'))}</div>")
        typed = st.text_input(t("insta.account"), key="ig_input", placeholder=t("insta.account_ph"),
                              label_visibility="collapsed")
        if known:
            st.pills(t("insta.known"), [a["username"] for a in known], key="ig_pick", on_change=_picked,
                     format_func=lambda u: f"@{u}", label_visibility="collapsed")
        st.html(f"<div class='rs-label'>{escape(t('insta.how_many'))}</div>")
        n = st.slider(t("insta.how_many"), im.MIN_TRACKS, im.MAX_TRACKS, 50, step=10, key="ig_n",
                      label_visibility="collapsed")
        audio = st.toggle(t("insta.audio_toggle"), value=ready["audio"], disabled=not ready["audio"], key="ig_audio")
        st.caption(t("insta.audio_help" if ready["audio"] else "insta.audio_todo"))
    account = im.username_of(typed)
    state = im.load(account) if account else None
    plan = im.estimate(n, state, ((state or {}).get("profile") or {}).get("media_count"), audio and ready["audio"])
    with mid:
        st.html(f"<div class='rs-est'><b class='num'>≈ {plan['seconds']:.0f} s</b>"
                f"<span>{escape(t('insta.estimate', n=fmt_int(n), posts=fmt_int(plan['posts']), new=fmt_int(plan['new'])))}</span></div>")
    with right:
        has = bool(state and state.get("tracks"))
        go = st.button(t("insta.again" if has else "insta.go", n=fmt_int(n)), key="ig_go", type="primary", width="stretch",
                       icon=":material/queue_music:", disabled=not ready["instagram"] or not account)
        st.caption(t("insta.keep_note") if ready["instagram"] else t("insta.needs_setup"))
    slot = st.empty()
    if typed.strip() and not account:
        slot.warning(t("insta.error_invalid", account=typed.strip()))
    elif go and account:
        extract(account, n, audio and ready["audio"], slot)

if not ready["instagram"]:
    with theme.panel("mist", "ig-setup"):
        theme.head(t("insta.setup_title"), t("insta.setup_meta"))
        st.markdown("\n".join(f"{i}. {t(f'insta.setup_{i}')}" for i in range(1, 8)))
        st.caption(t("insta.setup_note"))

# --- the playlist of the account ---------------------------------------------------------------------------
shown = account or current
state = im.load(shown) if shown else None
if not state or not state.get("posts"):
    with theme.panel("mist", "ig-empty"):
        st.html(f"<div class='rs-empty'>{studio.source_art('caption')}<b>{escape(t('insta.empty_title'))}</b>"
                f"<span>{escape(t('insta.empty_hint'))}</span></div>")
    st.stop()

notice = st.session_state.get("ig_notice") if st.session_state.get("ig_account") == shown else None
if notice:
    (st.warning if notice.startswith("audio_") or notice == "rate" else st.error)(t(f"insta.error_{notice}", account=shown))

profile = state.get("profile") or {}
pl = im.playlist(state)
by_source = pl["source"].value_counts().to_dict() if not pl.empty else {}
theme.section(t("insta.playlist_section"), t("insta.playlist_note"))
with theme.panel("rose", "ig-playlist"):
    pic = profile.get("picture")
    avatar = f"<img src='{escape(pic)}' alt=''>" if pic else "<span>@</span>"
    chips = "".join(f"<span class='ig-chip'><i style='background:{studio.SOURCE_COLORS[s]}'></i>"
                    f"{escape(t(f'insta.src_{s}'))} <b>{fmt_int(by_source.get(s, 0))}</b></span>" for s in SOURCES if by_source.get(s))
    followers = profile.get("followers")
    theme.html(f"<div class='ig-head'><div class='ig-avatar'>{avatar}</div><div class='ig-who'>"
               f"<b>{escape(profile.get('name') or shown)}</b>"
               f"<a href='https://www.instagram.com/{escape(shown)}/' target='_blank' rel='noopener'>@{escape(shown)} ↗</a>"
               f"<small>{escape(t('insta.followers', n=fmt_int(followers))) if followers else ''}</small></div>"
               f"<div class='ig-stats'><div><b class='num'>{fmt_int(len(pl))}</b><span>{escape(t('insta.stat_tracks'))}</span></div>"
               f"<div><b class='num'>{fmt_int(len(state['posts']))}</b><span>{escape(t('insta.stat_posts'))}</span></div>"
               f"<div><b class='num'>{escape(ago(state['updated'])) if state.get('updated') else '–'}</b>"
               f"<span>{escape(t('insta.stat_updated'))}</span></div></div></div>"
               f"<div class='ig-chips'>{chips}</div>")

if pl.empty:
    st.info(t("insta.nothing_found"))
    st.stop()

with theme.white("ig-table"):
    dates = pd.to_datetime(pl["post_at"], utc=True, errors="coerce").dt.tz_convert(data.timezone_name())
    rows = [{"track_id": r.track_id, "title": str(r.title or ""), "artist": str(r.artist_name or ""),
             "album": str(r.album_title or ""), "kind": r.kind, "at": str(r.post_at), "date": d.strftime("%d/%m/%Y") if pd.notna(d) else "",
             "source": r.source, "line": str(r.line or ""), "post": r.post_link, "link": r.link, "cover": r.cover or "",
             "posts": int(r.posts)} for r, d in zip(pl.itertuples(index=False), dates)]
    interactive.insta_table(rows, {"title": t("common.track"), "artist": t("common.artist"), "album": t("common.album"),
                                   "posted": t("insta.posted"), "found": t("insta.found_in"), "search": t("insta.table_search"),
                                   "count": t("reco.table_count"), "open": "Deezer", "post": "Instagram",
                                   "no_preview": t("reco.no_preview"), "play": t("reco.play"), "album_badge": t("common.album"),
                                   "sources": {s: t(f"insta.src_{s}") for s in SOURCES}, "times": t("insta.times")},
                            color, studio.SOURCE_COLORS)
    export = pd.DataFrame({
        t("insta.posted"): [r["date"] for r in rows], t("common.track"): pl["title"], t("common.artist"): pl["artist_name"],
        t("common.album"): pl["album_title"], t("insta.found_in"): [t(f"insta.src_{s}") for s in pl["source"]],
        t("insta.words"): pl["line"], "Instagram": pl["post_link"], "Deezer": pl["link"],
    })
    left, mid, right = st.columns([1, 1, 1.4], vertical_alignment="center")
    with left:
        ui.excel_download(export, f"insta_{shown}.xlsx", f"@{shown}"[:31], f"{t('rail.insta')} — @{shown}", key="ig_xl")
    with mid:
        text = "\n".join(f"{a} - {ti}" for a, ti in zip(pl["artist_name"], pl["title"]))
        st.download_button(t("insta.download_list"), text, file_name=f"insta_{shown}.txt", key="ig_txt",
                           icon=":material/playlist_add:")
    with right:
        with st.popover(t("insta.forget"), icon=":material/delete:"):
            st.caption(t("insta.forget_help", account=shown))
            if st.button(t("insta.forget_confirm"), key="ig_forget", type="primary"):
                im.forget(shown)
                st.session_state.pop("ig_account", None)
                st.session_state["ig_reset"] = True
                st.rerun()
st.caption(t("insta.footnote"))
