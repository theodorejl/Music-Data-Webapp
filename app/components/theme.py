"""Design system glue: loads app/assets/theme.css, page title row, sections, the
product mark, and the living pastel ground.

The look follows the taste-skill app run (style "pastel-consumer", shell "open plane"):
flat opaque panels, Manrope, sentence case, colour on data only. The living pastel
ground and the Explorations visuals are brand exceptions kept on the owner's request.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

from core.config import get_setting

ASSETS = Path(__file__).resolve().parents[1] / "assets"

# Pale tile + dark ink of the same hue (identity colours for genres, never chart series).
TILES = [
    ("#dcf1ff", "#0a3a80"),  # cobalt
    ("#fdeccd", "#7a3d06"),  # amber
    ("#d7f2f5", "#0e4a55"),  # teal
    ("#fde4ec", "#7a1f3d"),  # rose
    ("#e8f0d2", "#3d4a12"),  # olive
    ("#f1ece4", "#4a3f2f"),  # sand
]
NEUTRAL_TILE = ("#eef1f4", "#3a3d40")

_GRAIN = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/>"
    "<feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .5 0'/></filter>"
    "<rect width='100%25' height='100%25' filter='url(%23n)'/></svg>"
)


@lru_cache(maxsize=4)
def _css(mtime: float) -> str:
    return (ASSETS / "theme.css").read_text(encoding="utf-8")


def inject() -> None:
    css = _css((ASSETS / "theme.css").stat().st_mtime)
    # Grain sits on the living ground only (panels are opaque above it).
    grain = (f'.stApp::before{{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.07;'
             f'background-image:url("{_GRAIN}");mix-blend-mode:multiply}}')
    st.markdown(f"<style>{css}\n{grain}</style>", unsafe_allow_html=True)


def brand() -> None:
    st.logo(str(ASSETS / "logo.svg"), size="large")
    profile = get_setting("DEEZER_PROFILE")
    if profile:
        st.sidebar.markdown(f"<div class='ds-scope'>Profil <b>{escape(profile)}</b></div>", unsafe_allow_html=True)


def page_header(title: str, kicker: str | None = None, lead: str | None = None, dot: str | None = None) -> None:
    """Title row: a noun h1 at 28px and one grey line about the data (period, then the finding)."""
    st.title(title)
    parts = [escape(p) for p in (kicker, lead) if p]
    if parts:
        st.markdown(f"<p class='ds-sub'>{' · '.join(parts)}</p>", unsafe_allow_html=True)
    st.markdown("<div class='ds-section-gap'></div>", unsafe_allow_html=True)


def section(title: str, kicker: str | None = None) -> None:
    """A section heading at 20px regular; an optional grey note on the same line."""
    note = f"<span class='ds-card-meta'>{escape(kicker)}</span>" if kicker else ""
    st.markdown(f"<div class='ds-card-head' style='margin-top:28px'><h3 class='ds-card-title'>{escape(title)}</h3>{note}</div>",
                unsafe_allow_html=True)


def card_head(title: str, meta: str | None = None, figure: str | None = None, figure_sub: str | None = None) -> None:
    """Header of a white card: its title, its period or note, and the headline sum it explains."""
    html = f"<div class='ds-card-head'><h3 class='ds-card-title'>{escape(title)}</h3>"
    html += f"<span class='ds-card-meta'>{escape(meta)}</span></div>" if meta else "</div>"
    if figure:
        html += f"<div class='ds-figure num'>{figure}</div>"
    if figure_sub:
        html += f"<p class='ds-figure-sub'>{escape(figure_sub)}</p>"
    st.html(html)


def tile(i: int) -> tuple[str, str]:
    return TILES[i] if 0 <= i < len(TILES) else NEUTRAL_TILE


# --- living background (brand exception) ---------------------------------------------------------

PAGE_PALETTES = {
    "": ("#CBD2F6", "#F6D2BF", "#DCCFF2", "#C7E8D8"),
    "explore": ("#DCCFF2", "#F3CFDD", "#CBD2F6", "#F4E6B9"),
    "tops": ("#F6D2BF", "#F4E6B9", "#F3CFDD", "#DCCFF2"),
    "evolution": ("#C7E8D8", "#CBD2F6", "#F4E6B9", "#F6D2BF"),
    "habits": ("#F4E6B9", "#F6D2BF", "#C7E8D8", "#CBD2F6"),
    "discoveries": ("#F3CFDD", "#DCCFF2", "#C7E8D8", "#F4E6B9"),
    "wrapped": ("#F6D2BF", "#DCCFF2", "#CBD2F6", "#F4E6B9"),
    "library": ("#C7E8D8", "#F4E6B9", "#CBD2F6", "#F3CFDD"),
}
DEFAULT_PALETTE = ("#D6DAF2", "#E9DCEF", "#DDEBE4", "#F1E3D6")

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
    cv.style.background = `radial-gradient(70% 90% at 12% 18%, ${c[0]}, transparent 62%), radial-gradient(70% 90% at 88% 24%, ${c[1]}, transparent 62%), radial-gradient(80% 90% at 30% 92%, ${c[2]}, transparent 62%), radial-gradient(80% 90% at 82% 88%, ${c[3]}, transparent 62%), #F3F5F7`; };
  window.__dsbg = { set(p) { from = cur.map(c => c.slice()); to = p; mixT = 0; if (!gl) { cur = p; css(); } } };
  if (!gl) { css(); return; }
  const fs = `precision mediump float;uniform vec2 r;uniform float t;uniform vec3 a,b,c,d;
  float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
  float fbm(vec2 p){float v=0.,w=.5;for(int k=0;k<4;k++){v+=w*n(p);p*=2.03;w*=.5;}return v;}
  void main(){vec2 uv=gl_FragCoord.xy/r;vec2 q=uv*vec2(r.x/r.y,1.)*1.6;float s=t*.035;
  float f1=fbm(q+vec2(s,-s*.6));float f2=fbm(q*1.3+vec2(-s*.7,s*.4)+f1);float f3=fbm(q*.8+vec2(s*.2,s)+f2*.8);
  vec3 col=mix(a,b,smoothstep(.25,.75,f1));col=mix(col,c,smoothstep(.3,.8,f2)*.8);col=mix(col,d,smoothstep(.35,.85,f3)*.65);
  col=mix(col,vec3(.953,.961,.969),.52);gl_FragColor=vec4(col,1.);}`;
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


def background(page: str) -> None:
    """Fixed, slowly flowing pastel ground behind the whole app (one palette per page)."""
    palette = PAGE_PALETTES.get(page, DEFAULT_PALETTE)
    code = BG_JS.strip().removeprefix("<script>").removesuffix("</script>").replace("PALETTE", json.dumps(list(palette)))
    # Base64 keeps Streamlit's HTML sanitizer from mangling GLSL comparisons such as "k<4".
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    st.html(f"<script>(0, eval)(atob('{encoded}'))</script>", unsafe_allow_javascript=True)
