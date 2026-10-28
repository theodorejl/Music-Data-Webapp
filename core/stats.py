"""All stat queries.

`load_*` functions read the database (read-only). Everything else is a pure
function taking/returning pandas DataFrames, so it can be unit-tested and
cached by the app.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine

from core.models import Alias, Album, Artist, Play, SyncRun, Tag, Track, play_key

DIMENSIONS = ("artist", "album", "track", "genre")


# --- loading (DB -> DataFrames) ---------------------------------------------

@dataclass
class RawData:
    plays: pd.DataFrame
    artists: pd.DataFrame
    albums: pd.DataFrame
    tags: pd.DataFrame
    aliases: pd.DataFrame


def _read(engine: Engine, stmt) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def load_raw(engine: Engine) -> RawData:
    plays = _read(engine, select(
        Play.id.label("play_id"), Play.track_id, Play.played_at, Play.listened_seconds,
        Play.duration_is_estimated, Track.title.label("track_title"), Track.version.label("track_version"),
        Track.duration.label("track_duration"), Track.album_id, Track.artist_id, Track.isrc,
    ).join(Track, Track.id == Play.track_id, isouter=True))
    artists = _read(engine, select(Artist.id, Artist.name, Artist.picture_medium, Artist.picture_xl))
    albums = _read(engine, select(
        Album.id, Album.title, Album.artist_id, Album.release_date, Album.label,
        Album.cover_medium, Album.cover_xl, Album.deezer_genres,
    ))
    tags = _read(engine, select(Tag.entity_type, Tag.entity_id, Tag.tag, Tag.count, Tag.source))
    aliases = _read(engine, select(Alias.id, Alias.kind, Alias.source_key, Alias.target, Alias.created_at))
    return RawData(plays, artists, albums, tags, aliases)


def load_sync_runs(engine: Engine, limit: int = 200) -> pd.DataFrame:
    return _read(engine, select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit))


# --- aliases ---------------------------------------------------------------------

def _resolve_chain(mapping: dict[str, str], key: str) -> str:
    seen = set()
    while key in mapping and key not in seen:
        seen.add(key)
        key = mapping[key]
    return key


def apply_aliases(plays: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    """Hide plays and merge artists/albums (ids only; names joined afterwards)."""
    df = plays.copy()
    if aliases is None or aliases.empty or df.empty:
        return df
    by_kind = {k: dict(zip(g["source_key"].astype(str), g["target"].astype(str)))
               for k, g in aliases.groupby("kind")}

    hidden = set(by_kind.get("hide_play", {}))
    if hidden:
        keys = [play_key(int(t), pd.Timestamp(p).to_pydatetime()) for t, p in zip(df["track_id"], df["played_at"])]
        df = df[[k not in hidden for k in keys]]

    for col, kind in (("artist_id", "merge_artist"), ("album_id", "merge_album")):
        mapping = by_kind.get(kind)
        if mapping and col in df:
            df[col] = df[col].map(
                lambda v: int(_resolve_chain(mapping, str(int(v)))) if pd.notna(v) else v
            )
    return df


def album_genres(albums: pd.DataFrame, tags: pd.DataFrame, aliases: pd.DataFrame) -> dict[int, str]:
    """Primary genre per album id: forced alias > Deezer album genre >
    MusicBrainz album genre > MusicBrainz artist genre. Then genre renames."""
    forced, renames = {}, {}
    if aliases is not None and not aliases.empty:
        for kind, src, tgt in zip(aliases["kind"], aliases["source_key"], aliases["target"]):
            if kind == "album_genre":
                forced[int(src)] = tgt
            elif kind == "rename_genre":
                renames[src] = tgt

    def top_tag(entity_type: str) -> dict[int, str]:
        if tags is None or tags.empty:
            return {}
        t = tags[(tags["entity_type"] == entity_type) & (tags["source"] == "mb_genre")]
        t = t.sort_values("count", ascending=False, na_position="last").drop_duplicates("entity_id")
        return {int(k): v.title() for k, v in zip(t["entity_id"], t["tag"])}

    mb_album, mb_artist = top_tag("album"), top_tag("artist")
    out = {}
    for row in albums.itertuples(index=False):
        aid = int(row.id)
        genres = row.deezer_genres if isinstance(row.deezer_genres, list) else []
        genre = (forced.get(aid) or (genres[0] if genres else None) or mb_album.get(aid)
                 or (mb_artist.get(int(row.artist_id)) if pd.notna(row.artist_id) else None))
        if genre:
            out[aid] = _resolve_chain(renames, genre)
    return out


# --- assembled frame -------------------------------------------------------------

def assemble(raw: RawData, tz: str = "Europe/Zurich") -> pd.DataFrame:
    """One row per (visible) play, with aliases applied and metadata joined."""
    cols = ["play_id", "track_id", "played_at", "played_local", "listened_seconds", "minutes",
            "duration_is_estimated", "track_title", "track_duration", "artist_id", "artist_name",
            "artist_picture", "artist_picture_xl", "album_id", "album_title", "cover", "cover_xl", "genre"]
    if raw.plays.empty:
        return pd.DataFrame(columns=cols)
    df = apply_aliases(raw.plays, raw.aliases)
    # Genre is attached to the original album before album merges would hide it.
    genres = album_genres(raw.albums, raw.tags, raw.aliases)

    artists = raw.artists.rename(columns={"id": "artist_id", "name": "artist_name",
                                          "picture_medium": "artist_picture", "picture_xl": "artist_picture_xl"})
    albums = raw.albums.rename(columns={"id": "album_id", "title": "album_title",
                                        "cover_medium": "cover", "cover_xl": "cover_xl"})
    df = df.merge(artists, on="artist_id", how="left")
    df = df.merge(albums[["album_id", "album_title", "cover", "cover_xl"]], on="album_id", how="left")
    df["genre"] = df["album_id"].map(lambda a: genres.get(int(a)) if pd.notna(a) else None)

    df["played_at"] = pd.to_datetime(df["played_at"])
    df["played_local"] = df["played_at"].dt.tz_localize("UTC").dt.tz_convert(tz)
    df["listened_seconds"] = pd.to_numeric(df["listened_seconds"], errors="coerce").fillna(0)
    df["minutes"] = df["listened_seconds"] / 60.0
    df["duration_is_estimated"] = df["duration_is_estimated"].astype(bool)
    df["track_title"] = df["track_title"].fillna("?")
    df["artist_name"] = df["artist_name"].fillna("?")
    df["album_title"] = df["album_title"].fillna("?")
    return df[cols].sort_values("played_at", ascending=False).reset_index(drop=True)


def filter_frame(df: pd.DataFrame, start=None, end=None, min_seconds: float = 0) -> pd.DataFrame:
    """start/end: tz-aware Timestamps (end exclusive) in the display timezone."""
    out = df
    if start is not None:
        out = out[out["played_local"] >= start]
    if end is not None:
        out = out[out["played_local"] < end]
    if min_seconds:
        out = out[out["listened_seconds"] >= min_seconds]
    return out


# --- key figures -------------------------------------------------------------------

def kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"plays": 0, "minutes": 0.0, "artists": 0, "albums": 0, "tracks": 0,
                "avg_seconds": 0.0, "estimated_share": 0.0, "days": 0}
    return {
        "plays": int(len(df)),
        "minutes": float(df["minutes"].sum()),
        "artists": int(df["artist_id"].nunique()),
        "albums": int(df["album_id"].nunique()),
        "tracks": int(df["track_id"].nunique()),
        "avg_seconds": float(df["listened_seconds"].mean()),
        "estimated_share": float(df["duration_is_estimated"].mean()),
        "days": int(df["played_local"].dt.date.nunique()),
    }


_DIM_COLS = {
    "artist": ("artist_id", "artist_name", None, "artist_picture"),
    "album": ("album_id", "album_title", "artist_name", "cover"),
    "track": ("track_id", "track_title", "artist_name", "cover"),
    "genre": ("genre", "genre", None, None),
}


def top(df: pd.DataFrame, dim: str, metric: str = "plays", n: int = 10) -> pd.DataFrame:
    """Columns: rank, key, label, sublabel, image, plays, minutes."""
    key, label, sub, image = _DIM_COLS[dim]
    cols = ["rank", "key", "label", "sublabel", "image", "plays", "minutes"]
    data = df.dropna(subset=[key])
    if data.empty:
        return pd.DataFrame(columns=cols)
    agg = {"plays": ("play_id", "count"), "minutes": ("minutes", "sum"), "label": (label, "first")}
    if sub:
        agg["sublabel"] = (sub, "first")
    if image:
        agg["image"] = (image, "first")
    g = data.groupby(key).agg(**agg).reset_index().rename(columns={key: "key"})
    if "label" not in g or dim == "genre":
        g["label"] = g["key"]
    g["sublabel"] = g.get("sublabel", None)
    g["image"] = g.get("image", None)
    other = "minutes" if metric == "plays" else "plays"
    g = g.sort_values([metric, other], ascending=False).head(n).reset_index(drop=True)
    g["rank"] = g.index + 1
    return g[cols]


# --- evolution -------------------------------------------------------------------

_FREQ = {"D": "D", "W": "W-MON", "M": "MS"}


def _period(df: pd.DataFrame, freq: str) -> pd.Series:
    local = df["played_local"].dt.tz_localize(None)
    if freq == "D":
        return local.dt.normalize()
    if freq == "W":
        return (local - pd.to_timedelta(local.dt.weekday, unit="D")).dt.normalize()
    return local.dt.to_period("M").dt.to_timestamp()


def period_of(df: pd.DataFrame, freq: str) -> pd.Series:
    """The day, week (Monday) or month each play belongs to, as used by timeline()."""
    return _period(df, freq)


def timeline(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Plays and minutes per period, with empty periods filled with 0."""
    if df.empty:
        return pd.DataFrame(columns=["period", "plays", "minutes"])
    g = df.assign(period=_period(df, freq)).groupby("period").agg(
        plays=("play_id", "count"), minutes=("minutes", "sum"))
    full = pd.date_range(g.index.min(), g.index.max(), freq=_FREQ[freq])
    return g.reindex(full, fill_value=0).rename_axis("period").reset_index()


def cumulative(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    t = timeline(df, freq)
    if t.empty:
        return t
    t["plays"] = t["plays"].cumsum()
    t["minutes"] = t["minutes"].cumsum()
    return t


def share_over_time(df: pd.DataFrame, dim: str, freq: str = "M", top_n: int = 6,
                    metric: str = "plays", other_label: str = "Other") -> pd.DataFrame:
    """Long format: period, label, value, share (0..1). Top N overall, rest = other."""
    key, label, _, _ = _DIM_COLS[dim]
    data = df.dropna(subset=[key])
    if data.empty:
        return pd.DataFrame(columns=["period", "label", "value", "share"])
    tops = top(data, dim, metric, top_n)
    names = dict(zip(tops["key"], tops["label"]))
    value = data["minutes"] if metric == "minutes" else 1
    d = data.assign(period=_period(data, freq), value=value,
                    label=data[key].map(lambda k: names.get(k, other_label)))
    g = d.groupby(["period", "label"], as_index=False)["value"].sum()
    g["share"] = g["value"] / g.groupby("period")["value"].transform("sum")
    order = list(names.values()) + [other_label]
    g["label"] = pd.Categorical(g["label"], categories=order, ordered=True)
    return g.sort_values(["period", "label"]).reset_index(drop=True)


def ranks_over_time(df: pd.DataFrame, dim: str = "artist", freq: str = "M", n: int = 6,
                    metric: str = "minutes", depth: int = 10) -> pd.DataFrame:
    """Rank per period of the n overall leaders: period, label, image, rank (ranks deeper than
    `depth` are left out, so a line breaks when the leader drops out of sight)."""
    key, _, _, _ = _DIM_COLS[dim]
    data = df.dropna(subset=[key])
    if data.empty:
        return pd.DataFrame(columns=["period", "label", "image", "rank"])
    leaders = top(data, dim, metric, n)
    names = dict(zip(leaders["key"], leaders["label"]))
    value = data["minutes"] if metric == "minutes" else 1
    g = data.assign(period=_period(data, freq), value=value).groupby(["period", key])["value"].sum().reset_index()
    g["rank"] = g.groupby("period")["value"].rank(ascending=False, method="first")
    g = g[g[key].isin(list(names)) & (g["rank"] <= depth)].copy()
    g["label"] = g[key].map(names)
    g["image"] = g[key].map(dict(zip(leaders["key"], leaders["image"])))
    return g[["period", "label", "image", "rank"]].reset_index(drop=True)


def top_cover_by(df: pd.DataFrame, groups: pd.Series) -> dict:
    """For each group (a period, an hour...), the most played album: {group: (cover, title, artist)}."""
    d = df.assign(grp=groups).dropna(subset=["album_id"])
    if d.empty:
        return {}
    g = (d.groupby(["grp", "album_id"]).agg(n=("play_id", "count"), cover=("cover", "first"),
                                           title=("album_title", "first"), artist=("artist_name", "first"))
         .reset_index().sort_values("n", ascending=False).drop_duplicates("grp"))
    return {r.grp: (r.cover, r.title, r.artist) for r in g.itertuples(index=False)}


MOMENTS = (("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24))


def moments(df: pd.DataFrame) -> list[dict]:
    """The four moments of the day: minutes and most played album of each."""
    hour = df["played_local"].dt.hour
    out = []
    for name, h0, h1 in MOMENTS:
        part = df[(hour >= h0) & (hour < h1)]
        cover = top_cover_by(part, pd.Series(0, index=part.index)).get(0, (None, None, None))
        out.append({"name": name, "minutes": float(part["minutes"].sum()), "plays": int(len(part)),
                    "cover": cover[0], "title": cover[1], "artist": cover[2]})
    return out


def week_matrix(df: pd.DataFrame, metric: str = "plays") -> pd.DataFrame:
    """One row per weekday × hour with plays: weekday, hour, value, cover, title, artist."""
    cols = ["weekday", "hour", "value", "cover", "title", "artist"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    local = df["played_local"]
    slot = local.dt.weekday * 24 + local.dt.hour
    vals = (df["minutes"] if metric == "minutes" else pd.Series(1, index=df.index)).groupby(slot).sum()
    covers = top_cover_by(df, slot)
    rows = [(int(k) // 24, int(k) % 24, float(v), *covers.get(k, (None, None, None))) for k, v in vals.items()]
    return pd.DataFrame(rows, columns=cols)


# --- habits -------------------------------------------------------------------------

def heatmap(df: pd.DataFrame, metric: str = "plays") -> pd.DataFrame:
    """7 x 24 matrix (index weekday 0=Monday, columns hour)."""
    m = pd.DataFrame(0.0, index=range(7), columns=range(24))
    if df.empty:
        return m
    local = df["played_local"]
    vals = df["minutes"] if metric == "minutes" else pd.Series(1, index=df.index)
    g = vals.groupby([local.dt.weekday, local.dt.hour]).sum()
    for (wd, hr), v in g.items():
        m.loc[wd, hr] = v
    return m


def streaks(df: pd.DataFrame, today=None) -> dict:
    """Consecutive days with at least one play."""
    if df.empty:
        return {"current": 0, "longest": 0, "longest_start": None, "longest_end": None, "active_days": 0}
    days = sorted(set(df["played_local"].dt.date))
    best, best_start, best_end = 1, days[0], days[0]
    run_start, run_len = days[0], 1
    for prev, cur in zip(days, days[1:]):
        if (cur - prev).days == 1:
            run_len += 1
        else:
            run_start, run_len = cur, 1
        if run_len > best:
            best, best_start, best_end = run_len, run_start, cur
    today = today or pd.Timestamp.now(tz=df["played_local"].dt.tz).date()
    last = days[-1]
    current = 0
    if (today - last).days <= 1:
        current = 1
        for prev, cur in zip(reversed(days[:-1]), reversed(days)):
            if (cur - prev).days == 1:
                current += 1
            else:
                break
    return {"current": current, "longest": best, "longest_start": best_start,
            "longest_end": best_end, "active_days": len(days)}


SKIP_MARGIN = 8  # seconds of tolerance for crossfades and rounding between two plays


def skipped(df: pd.DataFrame) -> pd.Series:
    """A play is skipped when it stopped before the end of the track, however early or late.
    (Deezer's history itself never lists plays shorter than about 30 s.)"""
    duration = pd.to_numeric(df["track_duration"], errors="coerce")
    return duration.notna() & (df["listened_seconds"] < duration - SKIP_MARGIN)


def skip_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(skipped(df).mean())


def most_skipped(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["track_id", "track_title", "artist_name", "cover", "skips", "plays", "skip_rate"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    d = df.assign(skipped=skipped(df))
    g = d.groupby("track_id").agg(track_title=("track_title", "first"), artist_name=("artist_name", "first"),
                                  cover=("cover", "first"), skips=("skipped", "sum"), plays=("play_id", "count"))
    g = g[g["skips"] > 0]
    g["skip_rate"] = g["skips"] / g["plays"]
    return g.sort_values(["skips", "skip_rate"], ascending=False).head(n).reset_index()[cols]


# --- discoveries -----------------------------------------------------------------------

def first_listens(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """First play date per artist/album/track: key, label, sublabel, image, first_played, plays."""
    key, label, sub, image = _DIM_COLS[dim]
    cols = ["key", "label", "sublabel", "image", "first_played", "plays"]
    data = df.dropna(subset=[key])
    if data.empty:
        return pd.DataFrame(columns=cols)
    agg = {"label": (label, "first"), "first_played": ("played_local", "min"), "plays": ("play_id", "count")}
    if sub:
        agg["sublabel"] = (sub, "first")
    if image:
        agg["image"] = (image, "first")
    g = data.groupby(key).agg(**agg).reset_index().rename(columns={key: "key"})
    g["sublabel"] = g.get("sublabel", None)
    g["image"] = g.get("image", None)
    return g.sort_values("first_played", ascending=False).reset_index(drop=True)[cols]


def discoveries_per_month(df: pd.DataFrame) -> pd.DataFrame:
    """Number of new artists and albums (first ever play) per month."""
    if df.empty:
        return pd.DataFrame(columns=["period", "new_artists", "new_albums"])
    out = []
    for dim, col in (("artist", "new_artists"), ("album", "new_albums")):
        f = first_listens(df, dim)
        month = f["first_played"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
        out.append(month.value_counts().rename(col))
    res = pd.concat(out, axis=1).fillna(0).astype(int).sort_index()
    return res.rename_axis("period").reset_index()


# --- history table -------------------------------------------------------------------

def search_history(df: pd.DataFrame, query: str = "") -> pd.DataFrame:
    if not query:
        return df
    q = query.casefold()
    mask = (df["track_title"].str.casefold().str.contains(q, regex=False)
            | df["artist_name"].str.casefold().str.contains(q, regex=False)
            | df["album_title"].str.casefold().str.contains(q, regex=False)
            | df["genre"].fillna("").str.casefold().str.contains(q, regex=False))
    return df[mask]


def busiest_day(df: pd.DataFrame) -> tuple | None:
    if df.empty:
        return None
    g = df.groupby(df["played_local"].dt.date)["minutes"].sum()
    return g.idxmax(), float(g.max())


# --- library: favorite albums & playlists ------------------------------------------

@dataclass
class LibraryData:
    favorites: pd.DataFrame
    playlists: pd.DataFrame
    playlist_tracks: pd.DataFrame


def load_library(engine: Engine) -> LibraryData:
    from core.models import FavoriteAlbum, Playlist, PlaylistTrack

    favorites = _read(engine, select(
        FavoriteAlbum.album_id, FavoriteAlbum.added_at, Album.title, Album.artist_id,
        Artist.name.label("artist_name"), Album.release_date, Album.label, Album.record_type,
        Album.cover_medium, Album.cover_big, Album.cover_xl, Album.deezer_genres,
    ).join(Album, Album.id == FavoriteAlbum.album_id, isouter=True)
     .join(Artist, Artist.id == Album.artist_id, isouter=True))
    playlists = _read(engine, select(
        Playlist.id, Playlist.title, Playlist.creator_name, Playlist.is_own, Playlist.nb_songs,
        Playlist.duration, Playlist.picture, Playlist.added_at, Playlist.modified_at,
    ))
    tracks = _read(engine, select(
        PlaylistTrack.playlist_id, PlaylistTrack.position, PlaylistTrack.track_id, PlaylistTrack.added_at,
        Track.title.label("track_title"), Track.duration, Track.artist_id, Artist.name.label("artist_name"),
        Track.album_id, Album.title.label("album_title"), Album.cover_medium.label("cover"),
    ).join(Track, Track.id == PlaylistTrack.track_id, isouter=True)
     .join(Artist, Artist.id == Track.artist_id, isouter=True)
     .join(Album, Album.id == Track.album_id, isouter=True))
    return LibraryData(favorites, playlists, tracks)


def _plays_by(plays: pd.DataFrame, key: str) -> pd.DataFrame:
    if plays.empty:
        return pd.DataFrame(columns=[key, "plays", "minutes", "last_played"]).set_index(key)
    return plays.groupby(key).agg(plays=("play_id", "count"), minutes=("minutes", "sum"),
                                  last_played=("played_local", "max"))


def favorite_albums_view(lib: LibraryData, plays: pd.DataFrame, genres: dict[int, str] | None = None) -> pd.DataFrame:
    """One row per favorite album, with release year, genre and listening figures."""
    fav = lib.favorites.copy()
    if fav.empty:
        return fav.assign(genre=None, release_year=None, plays=0, minutes=0.0, last_played=None)
    fav["title"] = fav["title"].fillna("?")
    fav["artist_name"] = fav["artist_name"].fillna("?")
    release = pd.to_datetime(fav["release_date"], errors="coerce")
    fav["release_year"] = release.dt.year.astype("Int64")
    genres = genres or {}
    fav["genre"] = [genres.get(int(a)) if pd.notna(a) else None for a in fav["album_id"]]
    by_album = _plays_by(plays, "album_id")
    fav = fav.join(by_album, on="album_id")
    fav["plays"] = fav["plays"].fillna(0).astype(int)
    fav["minutes"] = fav["minutes"].fillna(0.0)
    return fav.sort_values("added_at", ascending=False, na_position="last").reset_index(drop=True)


def playlists_view(lib: LibraryData, plays: pd.DataFrame) -> pd.DataFrame:
    """One row per playlist: size, artists, and how much of it was listened to."""
    pl = lib.playlists.copy()
    if pl.empty:
        return pl.assign(tracks=0, artists=0, played_tracks=0, plays=0, played_share=0.0)
    pt = lib.playlist_tracks
    per_track = _plays_by(plays, "track_id")["plays"] if not plays.empty else pd.Series(dtype=int)
    t = pt.assign(plays=pt["track_id"].map(per_track).fillna(0).astype(int))
    agg = t.groupby("playlist_id").agg(tracks=("track_id", "count"), artists=("artist_id", "nunique"),
                                       played_tracks=("plays", lambda s: int((s > 0).sum())),
                                       plays=("plays", "sum"))
    pl = pl.join(agg, on="id")
    for col in ("tracks", "artists", "played_tracks", "plays"):
        pl[col] = pl[col].fillna(0).astype(int)
    pl["played_share"] = (pl["played_tracks"] / pl["tracks"].where(pl["tracks"] > 0)).fillna(0.0)
    return pl.sort_values(["plays", "added_at"], ascending=False).reset_index(drop=True)


def playlist_tracks_view(lib: LibraryData, plays: pd.DataFrame, playlist_id: int | None = None) -> pd.DataFrame:
    pt = lib.playlist_tracks
    if playlist_id is not None:
        pt = pt[pt["playlist_id"] == playlist_id]
    per_track = _plays_by(plays, "track_id")
    out = pt.join(per_track, on="track_id")
    out["plays"] = out["plays"].fillna(0).astype(int)
    out["minutes"] = out["minutes"].fillna(0.0)
    return out.sort_values(["playlist_id", "position"]).reset_index(drop=True)
