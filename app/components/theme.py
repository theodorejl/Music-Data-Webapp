"""Design system glue for the "Noto" direction (after fonts.google.com/noto).

White page under a slowly flowing pastel field; data lives in large, very round panels
filled with a grainy mesh gradient of one colour family each (see app/assets/theme.css);
oversized Google Sans Flex; data drawn in vivid pastels and in the deep ink of its panel.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"

# Colour families of the panels: vivid mid tone (data), deep ink (line art, figures), soft tint.
FAMILIES = {
    "sky": {"mid": "#1e9fd8", "ink": "#0a4f6b", "soft": "#dff3fc", "light": "#8fd2f1"},
    "coral": {"mid": "#ff6f4d", "ink": "#7a2410", "soft": "#ffe8df", "light": "#ffab8f"},
    "lilac": {"mid": "#8b6cf0", "ink": "#3a2584", "soft": "#eee9ff", "light": "#bba6ff"},
    "lime": {"mid": "#4fae2c", "ink": "#1f4f0f", "soft": "#eaf7da", "light": "#ade27c"},
    "rose": {"mid": "#e8558e", "ink": "#7d1a43", "soft": "#ffe6ef", "light": "#ffa8c8"},
    "butter": {"mid": "#d39a06", "ink": "#5c4100", "soft": "#fff3cf", "light": "#ffd66b"},
    "teal": {"mid": "#119f86", "ink": "#08493d", "soft": "#dcf5ee", "light": "#86dac6"},
    "mist": {"mid": "#5f6b7d", "ink": "#2b3442", "soft": "#eef2f7", "light": "#cdd8e8"},
    "night": {"mid": "#bba6ff", "ink": "#f2f0ff", "soft": "#2a2b4d", "light": "#8e7cf0"},
}
# Categorical order validated with the dataviz validator (CVD ΔE ≥ 9.9 between neighbours).
ORDER = ["sky", "coral", "lilac", "lime", "rose", "butter", "teal"]
PALETTE = [FAMILIES[f]["mid"] for f in ORDER]
OTHER = "#c4c9d0"

# One family per page, also used for its living background.
PAGE_FAMILY = {
    "": "sky", "home": "sky", "tops": "coral", "rhythms": "lime", "discoveries": "rose", "explore": "lilac",
    "wrapped": "butter", "library": "teal", "history": "mist", "artist": "lilac", "album": "coral",
    "track": "rose", "admin": "mist",
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
    css = _css((ASSETS / "theme.css").stat().st_mtime)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def brand() -> None:
    st.logo(str(ASSETS / "mark.svg"), size="large", icon_image=str(ASSETS / "mark.svg"))


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


# --- living background ------------------------------------------------------------------------

BG_JS = """
<script>
(() => {
  const target = PALETTE.map(h => [1,3,5].map(i => parseInt(h.slice(i, i + 2), 16) / 255));
  if (window.__dsbg) { window.__dsbg.set(target); return; }
  const cv = document.createElement('canvas'); cv.id = 'ds-bg'; document.body.prepend(cv);
  const gl = cv.getContext('webgl', {antialias: false, premultipliedAlpha: false});
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = target.map(c => c.slice()), from = cur, to = target, mixT = 1;
  const css = () => { const c = cur.map(v => `rgb(${v.map(x => Math.round(x * 255)).join(',')})`);
    cv.style.background = `radial-gradient(60% 70% at 10% 10%, ${c[0]}, transparent 62%), radial-gradient(60% 70% at 92% 18%, ${c[1]}, transparent 62%), radial-gradient(70% 80% at 30% 96%, ${c[2]}, transparent 62%), radial-gradient(70% 80% at 86% 92%, ${c[3]}, transparent 62%), #FFFFFF`; };
  window.__dsbg = { set(p) { from = cur.map(c => c.slice()); to = p; mixT = 0; if (!gl) { cur = p; css(); } } };
  if (!gl) { css(); return; }
  const fs = `precision mediump float;uniform vec2 r;uniform float t;uniform vec3 a,b,c,d;
  float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
  float fbm(vec2 p){float v=0.,w=.5;for(int k=0;k<4;k++){v+=w*n(p);p*=2.03;w*=.5;}return v;}
  void main(){vec2 uv=gl_FragCoord.xy/r;vec2 q=uv*vec2(r.x/r.y,1.)*1.4;float s=t*.04;
  float f1=fbm(q+vec2(s,-s*.6));float f2=fbm(q*1.3+vec2(-s*.7,s*.4)+f1);float f3=fbm(q*.8+vec2(s*.2,s)+f2*.8);
  vec3 col=mix(a,b,smoothstep(.25,.75,f1));col=mix(col,c,smoothstep(.3,.8,f2)*.85);col=mix(col,d,smoothstep(.35,.85,f3)*.7);
  float edge=smoothstep(.15,.95,length(uv-vec2(.5,.45))*1.25);
  col=mix(vec3(1.),col,.30+.42*edge);gl_FragColor=vec4(col,1.);}`;
  const sh = (ty, src) => { const o = gl.createShader(ty); gl.shaderSource(o, src); gl.compileShader(o); return o; };
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = n => gl.getUniformLocation(pr, n), ur = U('r'), ut = U('t'), uc = ['a','b','c','d'].map(U);
  const fit = () => { cv.width = Math.ceil(innerWidth / 4); cv.height = Math.ceil(innerHeight / 4);
    gl.viewport(0, 0, cv.width, cv.height); gl.uniform2f(ur, cv.width, cv.height); };
  addEventListener('resize', fit); fit();
  let last = 0; const t0 = performance.now();
  const frame = now => {
    if (!document.hidden && now - last > 50) {
      last = now;
      if (mixT < 1) { mixT = Math.min(1, mixT + 0.04); const e = 1 - Math.pow(1 - mixT, 3);
        cur = from.map((c, i) => c.map((v, j) => v + (to[i][j] - v) * e)); }
      uc.forEach((u, i) => gl.uniform3fv(u, cur[i]));
      gl.uniform1f(ut, still ? 20 : (now - t0) / 1000 + 20); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    if (!still || mixT < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  if (still) { uc.forEach((u, i) => gl.uniform3fv(u, cur[i])); gl.uniform1f(ut, 20); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); }
})();
</script>
"""

# Four vivid-pastel stops per page family for the living field.
BG_PALETTES = {
    "sky": ("#8fd2f1", "#ffc6dc", "#c3f0d9", "#b3cff6"),
    "coral": ("#ffab8f", "#ffd66b", "#ffc6dc", "#cfe2f6"),
    "lime": ("#ade27c", "#86dac6", "#ffe9a3", "#c4e9f9"),
    "rose": ("#ffa8c8", "#ddd2ff", "#ffd0bd", "#c4e9f9"),
    "lilac": ("#bba6ff", "#ffa8c8", "#8fd2f1", "#ffe9a3"),
    "butter": ("#ffd66b", "#ffab8f", "#ade27c", "#ffcde0"),
    "teal": ("#86dac6", "#c4e9f9", "#d4f0ae", "#ffd66b"),
    "mist": ("#cdd8e8", "#ddd2ff", "#c4e9f9", "#ffd0bd"),
}


def background(page: str) -> None:
    """Fixed, slowly flowing pastel field behind the whole app (one palette per page)."""
    palette = BG_PALETTES.get(PAGE_FAMILY.get(page, "sky"), BG_PALETTES["sky"])
    code = BG_JS.strip().removeprefix("<script>").removesuffix("</script>").replace("PALETTE", json.dumps(list(palette)))
    # Base64 keeps Streamlit's HTML sanitizer from mangling GLSL comparisons such as "k<4".
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    st.html(f"<script>(0, eval)(atob('{encoded}'))</script>", unsafe_allow_javascript=True)
