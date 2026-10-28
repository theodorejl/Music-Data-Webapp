"""Design system: tokens, global CSS for Streamlit widgets, page headers and the
animated shader-gradient hero.

Direction: soft stone ground, white surfaces separated by tone (no hairlines),
large regular-weight Geist display type with tight tracking, small spaced
uppercase labels, pastel tints, film grain, tactile "pushable" buttons and
restrained motion (transform/opacity only, reduced-motion fallback).
"""

from __future__ import annotations

import json
from html import escape

import streamlit as st

PASTELS = {  # tint (surfaces) / edge (button depth) / strong (charts, validated order)
    "periwinkle": ("#DDE2FB", "#AEB9F2", "#6C7FE8"),
    "peach": ("#FBE1D4", "#F2B99D", "#EE8E66"),
    "lavender": ("#E9E1F8", "#C6B4EC", "#9B7FD9"),
    "mint": ("#D4F0E3", "#9CD8BE", "#3FB58E"),
    "butter": ("#F7ECC8", "#E6CF84", "#D9A93A"),
    "rose": ("#F8DDE8", "#EDB0C7", "#E07FA8"),
}
ORDER = list(PASTELS)

_GRAIN = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/>"
    "<feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0'/></filter>"
    "<rect width='100%25' height='100%25' filter='url(%23n)'/></svg>"
)

CSS = """
<style>
:root {
  --bg: #EFEEEA; --surface: #FBFAF8; --surface-2: #F4F3EF; --ink: #17171A; --ink-2: #4A4843;
  --muted: #8A8780; --edge: #DAD7D0;
  --peri: #DDE2FB; --peri-e: #AEB9F2; --peach: #FBE1D4; --peach-e: #F2B99D;
  --lav: #E9E1F8; --lav-e: #C6B4EC; --mint: #D4F0E3; --mint-e: #9CD8BE;
  --butter: #F7ECC8; --butter-e: #E6CF84; --rose: #F8DDE8; --rose-e: #EDB0C7;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1); --ease-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --t-press: 140ms; --t-hover: 180ms; --t-ui: 240ms; --t-reveal: 800ms;
  --r-card: 26px; --r-field: 14px;
}

/* ---------- ground & grain ---------- */
html, body { background: var(--bg); }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent !important; }
.stApp::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 1; opacity: .11;
  background-image: url("GRAIN"); mix-blend-mode: multiply;
}
#ds-bg { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 0; pointer-events: none;
  transition: opacity 1.2s var(--ease-out); }
.stApp > * { position: relative; z-index: 2; }
[data-testid="stHeader"] { background: transparent; }
.stElementContainer:has(> [data-testid="stHtml"] > script:only-child) { display: none; }
[data-testid="stMainBlockContainer"] { max-width: none; padding: 2.2rem clamp(1.4rem, 3.2vw, 3.6rem) 6rem; }
:root { --glass: rgba(251, 250, 248, .74); --glass-2: rgba(251, 250, 248, .58); }
@media (max-width: 640px) { [data-testid="stMainBlockContainer"] { padding: 1.2rem 1rem 4rem; } }

/* ---------- type ---------- */
html { font-variant-numeric: tabular-nums; -webkit-font-smoothing: antialiased; }
h1 { font-weight: 400 !important; letter-spacing: -0.045em !important; line-height: .95 !important;
     font-size: clamp(2.6rem, 1.4rem + 3.6vw, 4.8rem) !important; text-wrap: balance; }
h2 { font-weight: 400 !important; letter-spacing: -0.035em !important; font-size: clamp(1.7rem, 1.2rem + 1.4vw, 2.4rem) !important; }
h3 { font-weight: 450 !important; letter-spacing: -0.025em !important; font-size: 1.3rem !important; }
[data-testid="stHeadingWithActionElements"] [data-testid="stHeaderActionElements"] { display: none; }
p, li { text-wrap: pretty; }
[data-testid="stCaptionContainer"] { color: var(--muted); }
.ds-kicker { font-family: "Geist Mono", ui-monospace, monospace; font-size: .72rem; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted); display: flex; gap: .9rem; align-items: center; margin: 0 0 .9rem; }
.ds-kicker i { width: .55rem; height: .55rem; border-radius: 99px; display: inline-block; background: var(--dot, var(--peri-e)); }
.ds-lead { font-size: clamp(1.05rem, .95rem + .4vw, 1.3rem); color: var(--ink-2); max-width: 56ch; line-height: 1.45;
  margin: 1rem 0 2.2rem; }
.ds-muted { color: var(--muted); font-size: .85rem; }
.ds-sub { color: var(--ink-2); font-size: 1.05rem; margin: .4rem 0 1rem; }
.ds-section { margin-top: 3.2rem; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: var(--glass-2) !important; backdrop-filter: blur(26px) saturate(1.2);
  -webkit-backdrop-filter: blur(26px) saturate(1.2); }
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebarHeader"] { padding-top: 1.4rem; }
[data-testid="stSidebarHeader"] img { height: 2rem !important; max-width: 13rem; }
[data-testid="stNavSectionHeader"] { font-family: "Geist Mono", monospace; font-size: .68rem !important;
  letter-spacing: .16em; text-transform: uppercase; color: var(--muted) !important; margin-top: 1rem; }
[data-testid="stSidebarNavLink"] { border-radius: 12px; transition: background var(--t-hover) var(--ease-out); }
[data-testid="stSidebarNavLink"]:hover { background: var(--surface-2); }
[data-testid="stSidebarNavLink"][aria-current="page"], [data-testid="stSidebarNavLink"].active { background: var(--peri); }
[data-testid="stSidebarNavSeparator"] { display: none; }
.ds-brand { font-size: 1.35rem; letter-spacing: -0.04em; font-weight: 450; margin: .2rem 0 .1rem; }
.ds-brand b { display: inline-block; width: .7rem; height: .7rem; border-radius: 99px; margin-right: .45rem;
  background: conic-gradient(from 40deg, #6C7FE8, #9B7FD9, #E07FA8, #EE8E66, #D9A93A, #3FB58E, #6C7FE8); }

/* ---------- cards ---------- */
[data-testid="stMetric"] {
  background: var(--glass); backdrop-filter: blur(22px) saturate(1.15); -webkit-backdrop-filter: blur(22px) saturate(1.15);
  border-radius: var(--r-card); padding: 1.15rem 1.35rem 1.25rem; position: relative;
  overflow: hidden; border: 0 !important; box-shadow: none !important;
}
[data-testid="stMetric"]::after { content: ""; position: absolute; right: -2.2rem; top: -2.2rem; width: 6.5rem; height: 6.5rem;
  border-radius: 999px; background: var(--tint, var(--peri)); opacity: .9; }
[data-testid="stMetricLabel"] { position: relative; z-index: 1; }
[data-testid="stMetricLabel"] p { font-family: "Geist Mono", monospace; font-size: .7rem !important;
  letter-spacing: .14em; text-transform: uppercase; color: var(--muted) !important; }
[data-testid="stMetricValue"] { position: relative; z-index: 1; letter-spacing: -0.04em; }
[data-testid="stColumn"]:nth-child(6n+1) [data-testid="stMetric"] { --tint: var(--peri); }
[data-testid="stColumn"]:nth-child(6n+2) [data-testid="stMetric"] { --tint: var(--peach); }
[data-testid="stColumn"]:nth-child(6n+3) [data-testid="stMetric"] { --tint: var(--mint); }
[data-testid="stColumn"]:nth-child(6n+4) [data-testid="stMetric"] { --tint: var(--lav); }
[data-testid="stColumn"]:nth-child(6n+5) [data-testid="stMetric"] { --tint: var(--butter); }
[data-testid="stColumn"]:nth-child(6n+6) [data-testid="stMetric"] { --tint: var(--rose); }
[data-testid="stPlotlyChart"] { background: var(--glass); backdrop-filter: blur(22px) saturate(1.15);
  -webkit-backdrop-filter: blur(22px) saturate(1.15); border-radius: var(--r-card); padding: 6px 14px; overflow: visible; }
[data-testid="stDataFrame"] { border-radius: 20px; overflow: hidden; background: var(--surface);
  box-shadow: 0 0 0 6px var(--glass-2); }
[data-testid="stImage"] img { border-radius: 16px; }
[data-testid="stExpander"] details { border: 0 !important; background: var(--surface); border-radius: 18px; }
[data-testid="stAlert"] > div { border-radius: 18px; border: 0; background: var(--surface) !important; color: var(--ink-2); }
[class*="st-key-card"] { background: var(--glass); backdrop-filter: blur(22px); border-radius: var(--r-card); padding: 1.4rem 1.5rem; }
[data-testid="stIFrame"], iframe[title*="components"] { border-radius: var(--r-card); }

/* ---------- fields ---------- */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="base-input"],
[data-testid="stNumberInputContainer"], [data-testid="stDateInputField"] {
  background: var(--surface) !important; border-radius: var(--r-field) !important; border-color: transparent !important; }
[data-testid="stWidgetLabel"] p { font-size: .82rem; color: var(--ink-2); }
[data-testid="stSlider"] [role="slider"] { box-shadow: 0 0 0 6px rgba(108,127,232,.15); }

/* ---------- tabs as pills ---------- */
[data-testid="stTabs"] [role="tablist"] { background: var(--glass); backdrop-filter: blur(18px); border-radius: 999px; padding: 5px; gap: 2px;
  width: fit-content; max-width: 100%; overflow-x: auto; }
[data-testid="stTab"] { border-radius: 999px; padding: .45rem 1.05rem !important; transition: background var(--t-ui) var(--ease-out), color var(--t-ui); }
[data-testid="stTab"] p { font-size: .9rem; }
[data-testid="stTab"][aria-selected="true"] { background: var(--ink); }
[data-testid="stTab"][aria-selected="true"] p { color: #fff !important; }
[data-testid="stTabs"] .react-aria-SelectionIndicator, [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }
[data-testid="stTabPanel"] { padding-top: 1.6rem; }

/* ---------- segmented controls ---------- */
[data-testid="stButtonGroup"] [role="radiogroup"] { background: var(--glass); backdrop-filter: blur(18px); border-radius: 999px; padding: 4px; gap: 2px; width: fit-content; }
button[data-variant="segmented_control"] { border: 0 !important; border-radius: 999px !important; background: transparent;
  transition: background var(--t-ui) var(--ease-out), color var(--t-ui); }
button[data-variant="segmented_control"][aria-checked="true"] { background: var(--ink) !important; }
button[data-variant="segmented_control"][aria-checked="true"] p { color: #fff !important; }

/* ---------- pushable buttons (uiverse-like, kept elegant) ---------- */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {
  --face: rgba(251,250,248,.85); --depth: var(--edge);
  position: relative; overflow: hidden; border: 0 !important; border-radius: 999px !important;
  background: var(--face) !important; color: var(--ink) !important; backdrop-filter: blur(12px); padding: .62rem 1.35rem !important;
  box-shadow: 0 4px 0 var(--depth), inset 0 1px 0 rgba(255,255,255,.8) !important;
  transform: translateY(0); transition: transform var(--t-press) var(--ease-out), box-shadow var(--t-press) var(--ease-out);
}
[data-testid="stBaseButton-primary"] { --face: var(--peri); --depth: var(--peri-e); }
[data-testid="stDownloadButton"] [data-testid="stBaseButton-secondary"] { --face: var(--mint); --depth: var(--mint-e); }
[data-testid="stBaseButton-primary"]::before, [data-testid="stBaseButton-secondary"]::before {
  content: ""; position: absolute; top: 0; left: -60%; width: 40%; height: 100%; pointer-events: none;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.75), transparent); transform: skewX(-18deg);
  opacity: 0; }
@media (hover: hover) and (pointer: fine) {
  [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-secondary"]:hover {
    transform: translateY(-2px); box-shadow: 0 6px 0 var(--depth), inset 0 1px 0 rgba(255,255,255,.8) !important; }
  [data-testid="stBaseButton-primary"]:hover::before, [data-testid="stBaseButton-secondary"]:hover::before {
    animation: ds-shine 900ms var(--ease-out) 1; }
}
[data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-secondary"]:active {
  transform: translateY(4px); box-shadow: 0 0 0 var(--depth) !important; }
@keyframes ds-shine { from { left: -60%; opacity: 1; } to { left: 130%; opacity: 1; } }
[data-testid="stBaseButton-tertiary"] { padding: 0 !important; min-height: 0 !important; color: var(--ink) !important; }
[data-testid="stBaseButton-tertiary"] p { text-decoration: underline; text-decoration-thickness: .07em;
  text-underline-offset: .2em; text-decoration-color: var(--edge); transition: text-decoration-color var(--t-hover); }
[data-testid="stBaseButton-tertiary"]:hover p { text-decoration-color: var(--ink); }
[data-testid="stPageLink-NavLink"] { border-radius: 999px; background: var(--surface); padding: .4rem 1rem; width: fit-content; }

/* ---------- cover grid ---------- */
.ds-card-title { font-weight: 500; line-height: 1.2; margin: .5rem 0 0; font-size: .92rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stElementContainer:has(.ds-card-sub) { margin-top: -1.1rem; }
.ds-card-sub { color: var(--muted); font-size: .8rem; margin: 0 0 .4rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
[data-testid="stImage"] img { transition: transform var(--t-ui) var(--ease-out); }
@media (hover: hover) and (pointer: fine) { [data-testid="stImage"]:hover img { transform: translateY(-3px) scale(1.015); } }

/* ---------- recap card ---------- */
.ds-hero-num { font-size: clamp(3rem, 1rem + 7vw, 6.5rem); letter-spacing: -0.05em; line-height: .9; font-weight: 400; }
.ds-wrapped { border-radius: 30px; padding: 2rem 2.2rem; margin-bottom: 1.4rem; position: relative; overflow: hidden;
  background: radial-gradient(120% 140% at 0% 0%, var(--peri) 0%, transparent 55%),
              radial-gradient(120% 140% at 100% 0%, var(--peach) 0%, transparent 55%),
              radial-gradient(140% 140% at 50% 120%, var(--mint) 0%, transparent 60%), var(--surface); }

/* ---------- motion ---------- */
@keyframes ds-rise { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
[data-testid="stMetric"], [data-testid="stPlotlyChart"], [data-testid="stIFrame"] { animation: ds-rise var(--t-reveal) var(--ease-expo) both; }
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { animation-delay: 70ms; }
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { animation-delay: 140ms; }
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { animation-delay: 210ms; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
@media (max-width: 640px) { [data-testid="stImage"] img { max-width: 200px; } .ds-hero-num { font-size: 3rem; } }
</style>
""".replace("GRAIN", _GRAIN)


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand() -> None:
    from pathlib import Path

    st.logo(str(Path(__file__).resolve().parents[1] / "assets" / "logo.svg"), size="large")


def page_header(title: str, kicker: str | None = None, lead: str | None = None, dot: str = "periwinkle") -> None:
    """Kicker line (small spaced caps), large display title, optional lead paragraph."""
    if kicker:
        st.markdown(f"<div class='ds-kicker' style='--dot:{PASTELS[dot][1]}'><i></i>{escape(kicker)}</div>",
                    unsafe_allow_html=True)
    st.title(title)
    if lead:
        st.markdown(f"<p class='ds-lead'>{escape(lead)}</p>", unsafe_allow_html=True)


def section(title: str, kicker: str | None = None) -> None:
    st.markdown("<div class='ds-section'></div>", unsafe_allow_html=True)
    if kicker:
        st.markdown(f"<div class='ds-kicker'>{escape(kicker)}</div>", unsafe_allow_html=True)
    st.subheader(title)


# --- animated shader-gradient hero ------------------------------------------------------

HERO_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300..600&family=Geist+Mono:wght@400&display=swap" rel="stylesheet">
<style>
html,body{margin:0;height:100%;overflow:hidden;background:transparent;font-family:Geist,system-ui,sans-serif;color:#17171A;
  font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
.wrap{position:absolute;inset:0;border-radius:30px;overflow:hidden}
canvas{position:absolute;inset:0;width:100%;height:100%}
.grain{position:absolute;inset:-50%;opacity:.16;mix-blend-mode:multiply;pointer-events:none;
  background-image:url("GRAIN");animation:g 1.2s steps(6) infinite}
@keyframes g{0%{transform:translate(0,0)}20%{transform:translate(-3%,2%)}40%{transform:translate(2%,-3%)}60%{transform:translate(-2%,-1%)}80%{transform:translate(3%,3%)}}
.content{position:absolute;inset:0;padding:clamp(22px,3.4vw,44px);display:flex;flex-direction:column;justify-content:space-between}
.kicker{font-family:"Geist Mono",monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(23,23,26,.62)}
h1{margin:0;font-weight:400;letter-spacing:-.05em;line-height:.9;font-size:clamp(46px,8.4vw,120px);max-width:12ch}
.stats{display:flex;gap:clamp(18px,4vw,56px);flex-wrap:wrap}
.stat .v{font-size:clamp(26px,3.4vw,46px);letter-spacing:-.04em;line-height:1}
.stat .l{font-family:"Geist Mono",monospace;font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;color:rgba(23,23,26,.6);margin-top:8px}
.rise{opacity:0;transform:translateY(22px);animation:r .9s cubic-bezier(.16,1,.3,1) forwards}
@keyframes r{to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){.rise{animation:none;opacity:1;transform:none}.grain{animation:none}}
</style></head><body><div class="wrap"><canvas id="c"></canvas><div class="grain"></div>
<div class="content"><div class="kicker rise">KICKER</div>
<div><h1 class="rise" style="animation-delay:.08s">TITLE</h1></div>
<div class="stats">STATS</div></div></div>
<script>
const C = COLORS;
const cv = document.getElementById('c'), gl = cv.getContext('webgl');
function hex(h){return [1,3,5].map(i=>parseInt(h.slice(i,i+2),16)/255)}
if (!gl) { cv.style.background = `radial-gradient(80% 120% at 10% 10%, ${C[0]}, transparent 60%), radial-gradient(80% 120% at 90% 20%, ${C[1]}, transparent 60%), radial-gradient(90% 120% at 50% 100%, ${C[2]}, ${C[3]})`; }
else {
const vs = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
const fs = `precision highp float;uniform vec2 r;uniform float t;uniform vec3 a,b,c,d;
vec3 m(vec3 x){return x-floor(x*(1./289.))*289.;}vec2 m(vec2 x){return x-floor(x*(1./289.))*289.;}vec3 pm(vec3 x){return m(((x*34.)+1.)*x);}
float sn(vec2 v){const vec4 C=vec4(.211324865405187,.366025403784439,-.577350269189626,.024390243902439);
vec2 i=floor(v+dot(v,C.yy));vec2 x0=v-i+dot(i,C.xx);vec2 i1=(x0.x>x0.y)?vec2(1.,0.):vec2(0.,1.);vec4 x12=x0.xyxy+C.xxzz;x12.xy-=i1;
i=m(i);vec3 p=pm(pm(i.y+vec3(0.,i1.y,1.))+i.x+vec3(0.,i1.x,1.));vec3 mm=max(.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.);
mm=mm*mm;mm=mm*mm;vec3 x=2.*fract(p*C.www)-1.;vec3 h=abs(x)-.5;vec3 ox=floor(x+.5);vec3 a0=x-ox;mm*=1.79284291400159-.85373472095314*(a0*a0+h*h);
vec3 g;g.x=a0.x*x0.x+h.x*x0.y;g.yz=a0.yz*x12.xz+h.yz*x12.yw;return 130.*dot(mm,g);}
void main(){vec2 uv=gl_FragCoord.xy/r;vec2 q=uv*vec2(r.x/r.y,1.)*1.15;float s=t*.045;
float n1=sn(q*.9+vec2(s,-s*.7));float n2=sn(q*1.4+vec2(-s*.8,s*.5)+n1*.6);float n3=sn(q*.6+vec2(s*.3,s)+n2*.5);
vec3 col=mix(a,b,smoothstep(-.6,.7,n1));col=mix(col,c,smoothstep(-.3,.8,n2)*.75);col=mix(col,d,smoothstep(.0,.9,n3)*.6);
col=mix(col,vec3(.98,.975,.965),.12+.18*uv.y);gl_FragColor=vec4(col,1.);}`;
function sh(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return s}
const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));gl.linkProgram(pr);gl.useProgram(pr);
const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
const loc=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
['a','b','c','d'].forEach((k,i)=>gl.uniform3fv(gl.getUniformLocation(pr,k),hex(C[i])));
const ur=gl.getUniformLocation(pr,'r'),ut=gl.getUniformLocation(pr,'t');
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;let t0=performance.now();
function fit(){const d=Math.min(devicePixelRatio,1.5);cv.width=cv.clientWidth*d;cv.height=cv.clientHeight*d;gl.viewport(0,0,cv.width,cv.height);gl.uniform2f(ur,cv.width,cv.height)}
addEventListener('resize',fit);fit();
function f(now){gl.uniform1f(ut,still?12.:(now-t0)/1000+12.);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);if(!still)requestAnimationFrame(f)}requestAnimationFrame(f);
}
</script></body></html>"""


def hero(title: str, kicker: str, stats: list[tuple[str, str]], palette: tuple[str, str, str, str] | None = None,
         height: int = 440) -> None:
    """Large rounded hero with a slowly flowing grainy pastel gradient (WebGL)."""
    palette = palette or ("#C9D0F7", "#F7CDB8", "#D7C8F2", "#BFE6D3")
    title = title[:1].upper() + title[1:]
    stat_html = "".join(
        f"<div class='stat rise' style='animation-delay:{.16 + i * .07:.2f}s'><div class='v'>{escape(v)}</div>"
        f"<div class='l'>{escape(label)}</div></div>" for i, (label, v) in enumerate(stats))
    html = (HERO_HTML.replace("GRAIN", _GRAIN).replace("KICKER", escape(kicker)).replace("TITLE", escape(title))
            .replace("STATS", stat_html).replace("COLORS", json.dumps(list(palette))))
    st.iframe(html, height=height)


# --- living background ----------------------------------------------------------------------

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
    cv.style.background = `radial-gradient(70% 90% at 12% 18%, ${c[0]}, transparent 62%), radial-gradient(70% 90% at 88% 24%, ${c[1]}, transparent 62%), radial-gradient(80% 90% at 30% 92%, ${c[2]}, transparent 62%), radial-gradient(80% 90% at 82% 88%, ${c[3]}, transparent 62%), #EFEEEA`; };
  window.__dsbg = { set(p) { from = cur.map(c => c.slice()); to = p; mixT = 0; if (!gl) { cur = p; css(); } } };
  if (!gl) { css(); return; }
  const fs = `precision mediump float;uniform vec2 r;uniform float t;uniform vec3 a,b,c,d;
  float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
  float fbm(vec2 p){float v=0.,w=.5;for(int k=0;k<4;k++){v+=w*n(p);p*=2.03;w*=.5;}return v;}
  void main(){vec2 uv=gl_FragCoord.xy/r;vec2 q=uv*vec2(r.x/r.y,1.)*1.6;float s=t*.035;
  float f1=fbm(q+vec2(s,-s*.6));float f2=fbm(q*1.3+vec2(-s*.7,s*.4)+f1);float f3=fbm(q*.8+vec2(s*.2,s)+f2*.8);
  vec3 col=mix(a,b,smoothstep(.25,.75,f1));col=mix(col,c,smoothstep(.3,.8,f2)*.8);col=mix(col,d,smoothstep(.35,.85,f3)*.65);
  col=mix(col,vec3(.937,.933,.918),.28);gl_FragColor=vec4(col,1.);}`;
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
    """Fixed, slowly flowing pastel gradient behind the whole app (one palette per page)."""
    import base64

    palette = PAGE_PALETTES.get(page, DEFAULT_PALETTE)
    code = BG_JS.strip().removeprefix("<script>").removesuffix("</script>").replace("PALETTE", json.dumps(list(palette)))
    # Base64 keeps Streamlit's HTML sanitizer from mangling GLSL comparisons such as "k<4".
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    st.html(f"<script>(0, eval)(atob('{encoded}'))</script>", unsafe_allow_javascript=True)
