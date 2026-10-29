"""Design system glue: a grainy pastel atlas (see app/assets/theme.css).

Each page has a colour family: a few neighbouring pastel hues melting into cream under a film
grain, as a living background swept by gusts, and in the large rounded panels that hold the
data. Titles in Rubik 80s Fade, text in Fira Code Medium, brush-stroke icons (icons.py), and one
player bar shared by every page for the 30 s previews.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"
APP_NAME = "DatAtlaSonore"

# Colour families: vivid mid tone (data), deep ink (line art, figures), soft tint, light (active
# states), and the three stops of their gradients (main hue, neighbouring hue, cream).
FAMILIES = {
    "sky": {"mid": "#1f97d1", "ink": "#0b4a66", "soft": "#dcf0fa", "light": "#9fd6f2", "stops": ("#5cbcec", "#8edbd6", "#f1ebdc")},
    "coral": {"mid": "#f25f3a", "ink": "#7a2410", "soft": "#ffe6dc", "light": "#ffb196", "stops": ("#ff8a68", "#ffbe86", "#f8eadb")},
    "lilac": {"mid": "#7d5ef0", "ink": "#3a2584", "soft": "#ece6ff", "light": "#c3b5fb", "stops": ("#9d8cf5", "#e0a6ea", "#f1eaf2")},
    "lime": {"mid": "#46a226", "ink": "#1f4f0f", "soft": "#e6f5d6", "light": "#bde69a", "stops": ("#95d466", "#d7e977", "#f3efda")},
    "rose": {"mid": "#e04a85", "ink": "#7d1a43", "soft": "#ffe2ed", "light": "#f9b5cf", "stops": ("#f487b4", "#f8b39a", "#f6e7e3")},
    "butter": {"mid": "#d39a06", "ink": "#5c4100", "soft": "#fff0c8", "light": "#ffdc85", "stops": ("#ffc94d", "#ffa866", "#f7eed8")},
    "teal": {"mid": "#0f9a80", "ink": "#08493d", "soft": "#d8f3ec", "light": "#95e0cf", "stops": ("#55cdb3", "#84d0ef", "#eff0df")},
    "mist": {"mid": "#5f6b7d", "ink": "#2b3442", "soft": "#ecf0f6", "light": "#c9d5e6", "stops": ("#a3b8d6", "#c7b6e6", "#f2efe8")},
    "ocean": {"mid": "#3f5fd8", "ink": "#1d2b7a", "soft": "#e1e7ff", "light": "#b0c0fb", "stops": ("#7591f6", "#6fcbe8", "#eff0f3")},
}
# Categorical order validated with the dataviz validator (CVD ΔE ≥ 9.9 between neighbours).
ORDER = ["sky", "coral", "lilac", "lime", "rose", "butter", "teal"]
PALETTE = [FAMILIES[f]["mid"] for f in ORDER]
OTHER = "#c4c9d0"

# One family per page, also used for its living background.
PAGE_FAMILY = {
    "": "sky", "home": "sky", "tops": "coral", "rhythms": "lime", "discoveries": "rose", "explore": "lilac",
    "wrapped": "butter", "library": "teal", "history": "mist", "artist": "lilac", "album": "coral",
    "track": "rose", "admin": "mist", "foryou": "ocean", "insta": "rose",
}


def ink(family: str) -> str:
    return FAMILIES.get(family, FAMILIES["mist"])["ink"]


def mid(family: str) -> str:
    return FAMILIES.get(family, FAMILIES["mist"])["mid"]


def family_of_color(color: str) -> str:
    for name, f in FAMILIES.items():
        if f["mid"] == color:
            return name
    return "mist"


@lru_cache(maxsize=4)
def _css(mtime: float) -> str:
    return (ASSETS / "theme.css").read_text(encoding="utf-8")


def inject() -> None:
    from app.components import icons

    css = _css((ASSETS / "theme.css").stat().st_mtime)
    st.markdown(f"<style>{icons.css()}{css}</style>", unsafe_allow_html=True)


def brand() -> None:
    st.logo(str(ASSETS / "mark.svg"), size="large", icon_image=str(ASSETS / "mark.svg"))


@lru_cache(maxsize=2)
def _mark_uri(mtime: float) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((ASSETS / "mark.svg").read_bytes()).decode("ascii")


def mark_img(size: int = 38) -> str:
    """The logo: a record that is the lens of a magnifying glass (its grooves turn in the SVG)."""
    uri = _mark_uri((ASSETS / "mark.svg").stat().st_mtime)
    return f"<img class='ds-mark' src='{uri}' width='{size}' height='{size}' alt=''>"


def brand_html() -> str:
    """DatAtlaSonore (Data · Atlas · Sonore) in Rubik 80s Fade, next to the logo."""
    return f"<div class='ds-brand'>{mark_img()}<b>{APP_NAME}</b></div>"


def html(content: str) -> None:
    """Raw HTML that may hold SVG (st.html strips SVG; markdown keeps it). One line, no blank lines."""
    st.markdown(content.replace("\n", " "), unsafe_allow_html=True)


# --- panels ---------------------------------------------------------------------------------

def panel(family: str, key: str):
    """A mesh-gradient panel (a Streamlit container: put anything inside)."""
    return st.container(key=f"p-{family}-{key}")


def white(key: str):
    """A plain white card, for long tables."""
    return st.container(key=f"w-{key}")


def head(title: str, meta: str | None = None, note: str | None = None) -> None:
    html = f"<div class='ds-head'><h3 class='ds-h'>{escape(title)}</h3>"
    html += f"<span class='ds-meta'>{escape(meta)}</span></div>" if meta else "</div>"
    if note:
        html += f"<p class='ds-note'>{escape(note)}</p>"
    st.html(html)


def figure(value: str, sub: str | None = None) -> None:
    """The headline number of a panel (value may hold a <small> unit)."""
    html = f"<div class='ds-figure num'>{value}</div>"
    if sub:
        html += f"<p class='ds-figure-sub'>{escape(sub)}</p>"
    st.html(html)


def section(title: str, note: str | None = None) -> None:
    """A big section title on the white page, between groups of panels."""
    html = f"<h2 class='ds-section'>{escape(title)}</h2>"
    if note:
        html += f"<p class='ds-section-note'>{escape(note)}</p>"
    st.html(html)


def gap(large: bool = False) -> None:
    st.html(f"<div class='{'ds-gap-l' if large else 'ds-gap'}'></div>")


def hero(family: str, title: str, lead: str | None = None, kicker: str | None = None,
         art: str | None = None, controls=None, ratio: tuple[float, float] = (1.15, 1)) -> None:
    """The page header: a large mesh panel with the title in oversized type, one sentence about
    the data (lead may contain <b>), the page's controls, and a data-drawn illustration on the right."""
    with st.container(key=f"hero-{family}"):
        left, right = st.columns(list(ratio), gap="large", vertical_alignment="center")
        with left:
            text = f"<div class='ds-kicker'><i></i>{escape(kicker)}</div>" if kicker else ""
            text += f"<h1 class='ds-hero-title'>{escape(title)}</h1>"
            if lead:
                text += f"<p class='ds-hero-lead'>{lead}</p>"
            st.html(text)
            if controls is not None:
                controls()
        with right:
            if art:
                html(f"<div class='ds-art'>{art}</div>")


# legacy names used by a few pages
def page_header(title: str, kicker: str | None = None, lead: str | None = None, dot: str | None = None,
                family: str = "mist") -> None:
    hero(family, title, escape(lead) if lead else None, kicker)


def card_head(title: str, meta: str | None = None, figure_: str | None = None, figure_sub: str | None = None) -> None:
    head(title, meta)
    if figure_:
        figure(figure_, figure_sub)


# --- living background, brush icons, player bar ----------------------------------------------------

BG_JS = r"""
(() => {
  const target = PALETTE.map(h => [1,3,5].map(i => parseInt(h.slice(i, i + 2), 16) / 255));
  if (window.__dsbg) { window.__dsbg.set(target); return; }
  const cv = document.createElement('canvas'); cv.id = 'ds-bg'; document.body.prepend(cv);
  const grain = document.createElement('div'); grain.id = 'ds-grain'; cv.after(grain);
  const gl = cv.getContext('webgl', {antialias: false, premultipliedAlpha: false});
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = target.map(c => c.slice()), from = cur, to = target, mixT = 1;
  const css = () => { const c = cur.map(v => `rgb(${v.map(x => Math.round(x * 255)).join(',')})`);
    cv.style.background = `radial-gradient(70% 80% at 90% 8%, ${c[0]}, transparent 66%), radial-gradient(60% 70% at 6% 40%, ${c[1]}, transparent 66%), ${c[2]}`; };
  window.__dsbg = { set(p) { from = cur.map(c => c.slice()); to = p; mixT = 0; if (!gl) { cur = p; css(); } } };
  if (!gl) { css(); return; }
  // A field of three colours that drifts, folds on itself, and is pushed here and there by gusts:
  // wide soft fronts that cross the screen in a few seconds, each time elsewhere and in another
  // direction, carrying whole areas of colour with them.
  const fs = `precision highp float;uniform vec2 r;uniform float t;uniform vec3 a,b,c;
  float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
  float fbm(vec2 p){float v=0.,w=.55;for(int k=0;k<4;k++){v+=w*n(p);p=p*1.9+vec2(1.7,9.2);w*=.45;}return v;}
  vec2 gust(vec2 q,float sd,float asp){float per=5.5+sd*2.1;float ph=(t+sd*17.)/per;float k=floor(ph);float f=fract(ph);
    float on=smoothstep(0.,.12,f)*(1.-smoothstep(.62,.8,f));float run=clamp(f/.78,0.,1.);
    float an=h(vec2(k,sd*3.1))*6.2832;vec2 dir=normalize(vec2(cos(an),sin(an)*.75));vec2 sid=vec2(-dir.y,dir.x);
    vec2 ctr=vec2(.5*asp,.5)+sid*(h(vec2(sd,k+3.))-.5)*.8;vec2 d=q-(ctr+dir*mix(-1.3,1.3,run)*max(1.,asp*.7));
    float al=dot(d,dir),ac=dot(d,sid);return dir*exp(-al*al/.16-ac*ac/(.3+.45*h(vec2(k,sd))))*on;}
  void main(){vec2 uv=gl_FragCoord.xy/r;float asp=r.x/r.y;vec2 q=uv*vec2(asp,1.);float s=t*.1;
  vec2 g=gust(q,1.,asp)+gust(q,2.,asp)+gust(q,3.,asp)+gust(q,4.,asp);
  vec2 p=q*.8-g*.8;
  vec2 w1=vec2(fbm(p+vec2(s,-.6*s)),fbm(p+vec2(-.7*s,.5*s)+4.3));
  vec2 w2=vec2(fbm(p+w1*1.3+vec2(1.7,9.2)+.3*s+g),fbm(p+w1*1.3+vec2(8.3,2.8)-.25*s));
  float f=fbm(p+w2*1.15);float e=fbm(p*.6+w1*.9-vec2(.22*s,.05*s)+g*.6);
  vec3 col=mix(c,a,smoothstep(.2,.6,f));col=mix(col,b,smoothstep(.38,.74,e)*.9);
  col=mix(col,c,smoothstep(.55,.95,(1.-f)*e*1.7)*.4);col=mix(col,c,smoothstep(.45,0.,uv.y)*.22);
  col+=.06*length(g);gl_FragColor=vec4(col,1.);}`;
  const sh = (ty, src) => { const o = gl.createShader(ty); gl.shaderSource(o, src); gl.compileShader(o); return o; };
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = n => gl.getUniformLocation(pr, n), ur = U('r'), ut = U('t'), uc = ['a','b','c'].map(U);
  const fit = () => { cv.width = Math.ceil(innerWidth / 3); cv.height = Math.ceil(innerHeight / 3);
    gl.viewport(0, 0, cv.width, cv.height); gl.uniform2f(ur, cv.width, cv.height); };
  addEventListener('resize', fit); fit();
  let last = 0; const t0 = performance.now();
  const frame = now => {
    if (!document.hidden && now - last > 33) {
      last = now;
      if (mixT < 1) { mixT = Math.min(1, mixT + 0.035); const e = 1 - Math.pow(1 - mixT, 3);
        cur = from.map((c, i) => c.map((v, j) => v + (to[i][j] - v) * e)); }
      uc.forEach((u, i) => gl.uniform3fv(u, cur[i]));
      gl.uniform1f(ut, still ? 30 : (now - t0) / 1000 + 30); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    if (!still || mixT < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  if (still) { uc.forEach((u, i) => gl.uniform3fv(u, cur[i])); gl.uniform1f(ut, 30); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); }
})();
"""

# Every Material icon Streamlit draws becomes its brush-stroke drawing (icons.py, theme.css).
ICONS_JS = r"""
(() => {
  if (window.__dsicons) return; window.__dsicons = true;
  const MAP = MATERIAL;
  let queued = false;
  const tag = () => { queued = false;
    document.querySelectorAll('[data-testid="stIconMaterial"]').forEach(el => {
      const name = (el.textContent || '').trim(); if (el.dataset.dsSrc === name) return;
      el.dataset.dsSrc = name; const ico = MAP[name];
      if (ico) { el.dataset.dsIcon = ico; el.style.setProperty('--ico', `var(--ico-${ico})`); }
      else { delete el.dataset.dsIcon; el.style.removeProperty('--ico'); } }); };
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(tag); } })
    .observe(document.body, {childList: true, subtree: true, characterData: true});
  tag();
})();
"""

# One player for the whole app: a thin bar at the bottom of the window that appears when a
# preview starts (pause, resume, seek, close) and keeps playing from one page to the next. The
# tables and maps (in their frames) drive it through window.parent.dsPlayer.
PLAYER_BAR_JS = r"""
(() => {
  const fam = FAMILY;
  if (window.dsPlayer) { window.dsPlayer.family(fam); return; }
  const bar = document.createElement('div'); bar.id = 'ds-player'; bar.className = 'ds-fam-' + fam;
  bar.innerHTML = `<button class="pl-btn" data-act="toggle" aria-label="play"><i data-ds-icon="play" style="--ico:var(--ico-play)"></i></button>
    <img class="pl-cover" alt=""><div class="pl-meta"><b></b><span></span></div>
    <span class="pl-t num">0:00</span><div class="pl-seek"><div class="pl-fill"></div><div class="pl-knob"></div></div><span class="pl-d num">0:30</span>
    <button class="pl-btn pl-close" data-act="close" aria-label="close"><i data-ds-icon="close" style="--ico:var(--ico-close)"></i></button>`;
  document.body.appendChild(bar);
  const audio = new Audio(); audio.preload = 'none';
  let st = {id: null, playing: false, loading: false, error: false, t: 0, d: 30, title: '', artist: '', cover: ''};
  const subs = new Set();
  const fmt = s => isFinite(s) ? Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0') : '0:00';
  const emit = () => { draw(); subs.forEach(fn => { try { fn(st); } catch (e) { subs.delete(fn); } }); };
  const q = s => bar.querySelector(s);
  function draw() {
    bar.classList.toggle('on', st.id !== null); bar.classList.toggle('playing', st.playing); bar.classList.toggle('loading', st.loading);
    const ico = q('[data-act="toggle"] i'), name = st.playing ? 'pause' : 'play';
    ico.dataset.dsIcon = name; ico.style.setProperty('--ico', `var(--ico-${name})`);
    q('.pl-meta b').textContent = st.title || '…'; q('.pl-meta span').textContent = st.artist || '';
    const img = q('.pl-cover'); if (st.cover && img.src !== st.cover) img.src = st.cover; img.style.visibility = st.cover ? 'visible' : 'hidden';
    q('.pl-t').textContent = fmt(st.t); q('.pl-d').textContent = fmt(st.d);
    const f = st.d ? Math.min(1, st.t / st.d) : 0; q('.pl-fill').style.width = (f * 100) + '%'; q('.pl-knob').style.left = (f * 100) + '%';
  }
  function jsonp(url) { return new Promise((res, rej) => { const cb = 'dzp' + Math.random().toString(36).slice(2);
    const s = document.createElement('script'); const tm = setTimeout(() => { delete window[cb]; s.remove(); rej('timeout'); }, 9000);
    window[cb] = d => { clearTimeout(tm); delete window[cb]; s.remove(); res(d); }; s.onerror = () => { clearTimeout(tm); rej('error'); };
    s.src = url + (url.includes('?') ? '&' : '?') + 'output=jsonp&callback=' + cb; document.head.appendChild(s); }); }
  async function play(id, meta) {
    audio.pause(); st = {...st, id, playing: false, loading: true, error: false, t: 0, d: 30,
      title: (meta && meta.title) || '', artist: (meta && meta.artist) || '', cover: (meta && meta.cover) || ''}; emit();
    try { const d = await jsonp('https://api.deezer.com/track/' + id); if (st.id !== id) return;
      if (!d || !d.preview) throw 'none';
      st.title = st.title || d.title_short || d.title || ''; st.artist = st.artist || (d.artist || {}).name || '';
      st.cover = st.cover || (d.album || {}).cover_medium || (d.album || {}).cover_small || '';
      audio.src = d.preview; await audio.play(); if (st.id !== id) return; st.loading = false; st.playing = true; emit(); }
    catch (e) { if (st.id === id) { st = {...st, loading: false, playing: false, error: true}; emit(); setTimeout(() => { if (st.id === id && st.error) api.close(); }, 2600); } }
  }
  const api = {
    toggle(id, meta) { if (st.id === id && !st.error) { st.playing ? api.pause() : api.resume(); } else play(id, meta); },
    play, pause() { audio.pause(); st.playing = false; emit(); },
    resume() { if (st.id === null) return; audio.play().then(() => { st.playing = true; emit(); }).catch(() => {}); },
    seek(frac) { if (audio.duration) { audio.currentTime = Math.max(0, Math.min(.999, frac)) * audio.duration; st.t = audio.currentTime; emit(); } },
    close() { audio.pause(); st = {...st, id: null, playing: false, loading: false}; emit(); },
    sub(fn) { subs.add(fn); try { fn(st); } catch (e) {} return () => subs.delete(fn); },
    get state() { return st; },
    family(f) { bar.className = bar.className.replace(/ds-fam-\S+/, 'ds-fam-' + f); },
  };
  audio.addEventListener('timeupdate', () => { st.t = audio.currentTime; st.d = audio.duration || 30; emit(); });
  audio.addEventListener('ended', () => { st.playing = false; st.t = st.d; emit(); });
  bar.addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (!b) return;
    if (b.dataset.act === 'toggle') { st.playing ? api.pause() : (st.t >= st.d - .05 ? (audio.currentTime = 0, api.resume()) : api.resume()); }
    if (b.dataset.act === 'close') api.close(); });
  const seekAt = e => { const r = q('.pl-seek').getBoundingClientRect(); api.seek((e.clientX - r.left) / r.width); };
  let dragging = false;
  q('.pl-seek').addEventListener('pointerdown', e => { dragging = true; q('.pl-seek').setPointerCapture(e.pointerId); seekAt(e); });
  q('.pl-seek').addEventListener('pointermove', e => { if (dragging) seekAt(e); });
  q('.pl-seek').addEventListener('pointerup', () => { dragging = false; });
  // any element of the page with data-ds-play="<track id>" plays that track
  document.addEventListener('click', e => { const el = e.target.closest('[data-ds-play]'); if (!el) return;
    e.preventDefault(); api.toggle(+el.dataset.dsPlay, {title: el.dataset.title, artist: el.dataset.artist, cover: el.dataset.cover}); });
  window.dsPlayer = api; draw();
})();
"""


def background(page: str) -> None:
    """The living field behind the app (the page's family), the brush icons and the player bar."""
    from app.components import icons

    family = PAGE_FAMILY.get(page, "sky")
    stops = FAMILIES.get(family, FAMILIES["sky"])["stops"]
    code = (BG_JS.replace("PALETTE", json.dumps(list(stops))) + ICONS_JS.replace("MATERIAL", json.dumps(icons.MATERIAL))
            + PLAYER_BAR_JS.replace("FAMILY", json.dumps(family)))
    # Base64 keeps Streamlit's HTML sanitizer from mangling GLSL comparisons such as "k<4".
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    st.html(f"<script>(0, eval)(atob('{encoded}'))</script>", unsafe_allow_javascript=True)
