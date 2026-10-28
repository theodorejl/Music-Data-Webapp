"""Original visualisations rendered as self-contained HTML/JS components.

- listening_spiral: every play is a dot on a time spiral (one turn = one day or week,
  angle = time of day), sized by listening time, coloured by genre.
- cover_orbit: album covers on a golden-angle spiral, sized by plays, slowly orbiting.
- artist_constellation: one particle per play, gathered in a drifting cloud per artist;
  the pointer pushes particles away.
- fingerprint_svg: generative "listening fingerprint" (one distorted ring per hour of
  the day), computed in Python so it can be downloaded as SVG.
"""

from __future__ import annotations

import json
import math
import random
from html import escape

import pandas as pd
import streamlit as st

STRONG = ["#1e9fd8", "#ff6f4d", "#8b6cf0", "#4fae2c", "#e8558e", "#d39a06", "#119f86"]  # validated chart order
OTHER = "#c4c9d0"
FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@300..700'
         '&display=swap" rel="stylesheet">')
BASE_CSS = """html,body{margin:0;background:transparent;font-family:'Geist Mono',ui-monospace,Menlo,monospace;color:#1f1f1f;
-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;overflow:hidden}
.card{position:relative;background:rgba(255,255,255,.5);border-radius:22px;overflow:hidden}
.lab{font-size:13px;color:#5c6064}
.legend{position:absolute;left:22px;top:20px;display:flex;flex-direction:column;gap:7px;z-index:2}
.legend span{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#4A4843}
.legend i{width:9px;height:9px;border-radius:9px;display:inline-block}
.tip{position:absolute;pointer-events:none;background:#17171A;color:#fff;padding:9px 12px;border-radius:12px;font-size:12.5px;
line-height:1.35;opacity:0;transform:translateY(4px);transition:opacity .18s,transform .18s cubic-bezier(.22,1,.36,1);max-width:260px;z-index:5}
.tip.on{opacity:1;transform:none}.tip small{color:rgba(255,255,255,.62);display:block}
.corner{position:absolute;right:22px;top:20px;text-align:right;z-index:2}"""


def _palette(labels: list[str]) -> dict[str, str]:
    """Genres keep the colour they have in every chart of the app."""
    try:
        from app.components.charts import category_colors

        return category_colors(list(labels))
    except Exception:
        return {lab: STRONG[i] if i < len(STRONG) else OTHER for i, lab in enumerate(labels)}


def _legend(colors: dict[str, str], other: str | None) -> str:
    items = "".join(f"<span><i style='background:{c}'></i>{escape(str(k))}</span>" for k, c in colors.items()
                    if c != OTHER)
    if other:
        items += f"<span><i style='background:{OTHER}'></i>{escape(other)}</span>"
    return f"<div class='legend'>{items}</div>"


# --- 1. time spiral -----------------------------------------------------------------------

def listening_spiral(df: pd.DataFrame, labels: dict, height: int = 680) -> None:
    """labels: {'other', 'turn_day', 'turn_week', 'hours': [4 labels], 'days': [7 labels], 'minutes'}."""
    if df.empty:
        return
    d = df.sort_values("played_at")
    local = d["played_local"]
    span_days = (local.max() - local.min()).total_seconds() / 86400
    weekly = span_days > 75
    top_genres = d["genre"].dropna().value_counts().head(6).index.tolist()
    colors = _palette(top_genres)
    start = local.min().normalize()
    pts = []
    for row in d.itertuples(index=False):
        t = row.played_local
        frac_day = (t.hour * 3600 + t.minute * 60 + t.second) / 86400
        if weekly:
            turn = ((t - start).days + frac_day) / 7
            angle = (t.weekday() + frac_day) / 7
        else:
            turn = (t - start).days + frac_day
            angle = frac_day
        pts.append([round(turn, 4), round(angle, 5), round(float(row.minutes), 2),
                    colors.get(row.genre, OTHER), escape(f"{row.track_title} — {row.artist_name}"),
                    t.strftime("%d/%m/%Y %H:%M")])
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
canvas{{display:block;width:100%;height:{height}px}}</style></head><body><div class="card">
{_legend(colors, labels['other'])}
<div class="corner"><div class="lab">{escape(labels['turn_week'] if weekly else labels['turn_day'])}</div>
<div style="font-size:12.5px;color:#4A4843;margin-top:6px">{escape(labels['minutes'])}</div></div>
<canvas id="c"></canvas><div class="tip" id="tip"></div></div>
<script>
const P={json.dumps(pts, ensure_ascii=False)}, H={json.dumps(labels['days'] if weekly else labels['hours'], ensure_ascii=False)}, WEEK={str(weekly).lower()};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
let W,Hh,cx,cy,R0,R1,maxTurn=Math.max(1,...P.map(p=>p[0]));let pos=[];
function fit(){{const d=devicePixelRatio||1;W=cv.clientWidth;Hh=cv.clientHeight;cv.width=W*d;cv.height=Hh*d;ctx.setTransform(d,0,0,d,0,0);
cx=W/2;cy=Hh/2+6;R1=Math.min(W,Hh)/2-46;R0=R1*0.12;
pos=P.map(p=>{{const a=p[1]*Math.PI*2-Math.PI/2;const r=R0+(R1-R0)*(p[0]/maxTurn);return[cx+Math.cos(a)*r,cy+Math.sin(a)*r,Math.max(1.6,Math.sqrt(p[2])*2.1)]}})}}
function guide(){{ctx.strokeStyle='rgba(23,23,26,.07)';ctx.lineWidth=1;ctx.beginPath();
const turns=Math.ceil(maxTurn);for(let i=0;i<=turns*120;i++){{const tt=i/120;const a=(tt%1)*Math.PI*2-Math.PI/2;const r=R0+(R1-R0)*(tt/maxTurn);
const x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r;i?ctx.lineTo(x,y):ctx.moveTo(x,y)}}ctx.stroke();
ctx.fillStyle='#5c6064';ctx.font='12px Geist Mono, ui-monospace, monospace';ctx.textAlign='center';ctx.textBaseline='middle';
H.forEach((h,i)=>{{const a=i/H.length*Math.PI*2-Math.PI/2;ctx.fillText(h,cx+Math.cos(a)*(R1+24),cy+Math.sin(a)*(R1+24))}})}}
let shown=still?P.length:0,hover=-1;
function draw(){{ctx.clearRect(0,0,W,Hh);guide();
for(let i=0;i<shown;i++){{const[x,y,r]=pos[i];ctx.globalAlpha=i===hover?1:.82;ctx.fillStyle=P[i][3];ctx.beginPath();ctx.arc(x,y,i===hover?r+2.5:r,0,7);ctx.fill()}}
ctx.globalAlpha=1;if(hover>=0){{const[x,y,r]=pos[hover];ctx.strokeStyle='#17171A';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,r+6,0,7);ctx.stroke()}}}}
fit();addEventListener('resize',()=>{{fit();draw()}});
const t0=performance.now();function anim(n){{shown=Math.min(P.length,Math.floor(P.length*Math.min(1,Math.max(0,(n-t0)/1800))**.7));draw();if(shown<P.length)requestAnimationFrame(anim)}}
still?draw():requestAnimationFrame(anim);
cv.addEventListener('mousemove',e=>{{const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;let best=-1,bd=196;
pos.forEach((p,i)=>{{const dd=(p[0]-mx)**2+(p[1]-my)**2;if(dd<bd){{bd=dd;best=i}}}});
if(best!==hover){{hover=best;draw()}}if(best>=0){{const p=P[best];tip.innerHTML=`${{p[4]}}<small>${{p[5]}} · ${{p[2].toFixed(1)}} min</small>`;
tip.style.left=Math.min(mx+14,W-270)+'px';tip.style.top=(my+14)+'px';tip.classList.add('on')}}else tip.classList.remove('on')}});
cv.addEventListener('mouseleave',()=>{{hover=-1;tip.classList.remove('on');draw()}});
</script></body></html>"""
    st.iframe(html, height=height + 4)


# --- 2. cover orbit ---------------------------------------------------------------------------

def cover_orbit(items: pd.DataFrame, plays_label: str, height: int = 660) -> None:
    """items: stats.top(df, 'album') frame (label, sublabel, image, plays)."""
    items = items[items["image"].notna()].head(64)
    if items.empty:
        return
    data = [[escape(str(r.label)), escape(str(r.sublabel or "")), r.image.replace("250x250", "500x500") if isinstance(r.image, str) else "",
             int(r.plays)] for r in items.itertuples()]
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
.stage{{position:relative;height:{height}px}}
.ring{{position:absolute;left:50%;top:50%;border-radius:50%;border:1px solid rgba(23,23,26,.07);transform:translate(-50%,-50%)}}
.orbit{{position:absolute;left:50%;top:50%;width:0;height:0;animation:spin 240s linear infinite}}
.it{{position:absolute;transform:translate(-50%,-50%);transition:transform .35s cubic-bezier(.22,1,.36,1);cursor:pointer}}
.it .face{{animation:spin 240s linear infinite reverse}}
.it img{{display:block;width:100%;height:100%;object-fit:cover;border-radius:10px;
box-shadow:0 10px 24px -14px rgba(23,23,26,.45);animation:float 7s ease-in-out infinite;animation-delay:var(--d)}}
.it:hover{{z-index:10;transform:translate(-50%,-50%) scale(1.55)}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}@keyframes float{{50%{{transform:translateY(-5px)}}}}
.center{{position:absolute;left:50%;bottom:22px;transform:translateX(-50%);text-align:center;min-height:40px}}
.center b{{display:block;font-weight:450;font-size:15px;letter-spacing:-.01em}}
@media (prefers-reduced-motion: reduce){{.orbit,.it .face,.it img{{animation:none}}}}</style></head>
<body><div class="card stage" id="s"><div class="center" id="cap"><span class="lab">{escape(plays_label)}</span></div></div>
<script>
const D={json.dumps(data, ensure_ascii=False)};const s=document.getElementById('s'),cap=document.getElementById('cap');
const W=s.clientWidth,H={height},R=Math.min(W,H)/2-40,maxP=Math.max(...D.map(d=>d[3])),minP=Math.min(...D.map(d=>d[3]));
[0.33,0.66,1].forEach(f=>{{const r=document.createElement('div');r.className='ring';r.style.width=r.style.height=(R*2*f)+'px';s.appendChild(r)}});
const o=document.createElement('div');o.className='orbit';s.appendChild(o);
const ga=Math.PI*(3-Math.sqrt(5)),n=D.length;
D.forEach((d,i)=>{{const r=R*0.92*Math.sqrt((i+.6)/n),a=i*ga;const k=maxP>minP?(d[3]-minP)/(maxP-minP):1;
const size=Math.round(30+k*Math.min(96,R*.32));const el=document.createElement('div');el.className='it';
el.style.left=(Math.cos(a)*r)+'px';el.style.top=(Math.sin(a)*r)+'px';el.style.width=el.style.height=size+'px';el.style.zIndex=Math.round(k*9);
el.innerHTML=`<div class="face" style="width:100%;height:100%"><img src="${{d[2]}}" alt="" style="--d:${{(i%7)*-1}}s" loading="lazy"></div>`;
el.onmouseenter=()=>cap.innerHTML=`<b>${{d[0]}}</b><span class="lab">${{d[1]}} · ${{d[3]}} {escape(plays_label)}</span>`;
el.onmouseleave=()=>cap.innerHTML=`<span class="lab">{escape(plays_label)}</span>`;o.appendChild(el)}});
</script></body></html>"""
    st.iframe(html, height=height + 4)


# --- 3. artist constellation (genre territories) ------------------------------------------

GLOW = ["#7fd0f5", "#ff9e85", "#b9a6ff", "#98dd72", "#ff8fbb", "#ffd25e", "#5fdcc2"]  # STRONG, made luminous for the night card
GLOW_OTHER = "#C9C4D8"


def artist_constellation(df: pd.DataFrame, labels: dict, height: int = 680) -> None:
    """Genres are territories (Voronoi cells, labelled); inside, each artist is a glowing
    cloud with one particle per play. Wheel or pinch to zoom, drag to move, double-click to
    come back; hovering a cloud names the artist (with their photo) without moving anything.
    labels: {'plays', 'artists', 'other', 'hint'}."""
    from app.components.interactive import ESC_JS, TERRITORY_JS, ZOOM_CSS, ZOOM_HTML, ZOOM_JS, js_data

    if df.empty:
        return
    genres = df["genre"].dropna().value_counts().head(6).index.tolist()
    base = _palette(genres)
    gcol = {g: GLOW[STRONG.index(base[g])] if base[g] in STRONG else GLOW_OTHER for g in genres}
    d = df.assign(group=df["genre"].where(df["genre"].isin(genres), labels["other"]))
    by_artist = d.groupby("artist_name").agg(plays=("play_id", "count"), picture=("artist_picture", "first"),
                                             group=("group", lambda s: s.mode().iloc[0]))
    by_artist = by_artist.sort_values("plays", ascending=False).head(48).reset_index()
    groups = [g for g in genres if g in set(by_artist["group"])]
    if labels["other"] in set(by_artist["group"]):
        groups.append(labels["other"])
    weight = by_artist.groupby("group")["plays"].sum()
    total = int(by_artist["plays"].sum())
    scale = min(14.0, 3600 / max(total, 1))
    G = [[str(g), gcol.get(g, GLOW_OTHER), int(weight.get(g, 0))] for g in groups]
    A = [[str(r.artist_name), int(r.plays), max(10, int(r.plays * scale)), groups.index(r.group),
          r.picture if isinstance(r.picture, str) else ""] for r in by_artist.itertuples()]
    caption = f"{total} {labels['plays']} · {len(A)} {labels['artists']}"
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
.night{{position:relative;border-radius:22px;overflow:hidden;background:radial-gradient(120% 90% at 50% 40%,#231C38 0%,#130F1E 60%,#0D0A15 100%)}}
canvas{{display:block;width:100%;height:{height}px}}
.cap{{position:absolute;right:22px;top:20px;font-size:12px;color:rgba(255,255,255,.7)}}
.tip{{background:#FBFAF8;color:#17171A;display:flex;gap:12px;align-items:center;padding:9px 14px 9px 9px}}.tip small{{color:#8A8780}}
.tip img{{width:48px;height:48px;border-radius:50%;object-fit:cover}}
{ZOOM_CSS}</style></head><body>
<div class="night"><canvas id="c"></canvas><div class="cap">{escape(caption)}</div><div class="tip" id="tip"></div>
{ZOOM_HTML}<div class="hint">{escape(labels["hint"])}</div></div>
<script>
const G={js_data(G)}, A={js_data(A)};{ESC_JS}
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
let W=0,H=0,cells=[],C=[],P=[],sprites={{}},hoverA=-1,hoverG=-1;const M=30;
{TERRITORY_JS}
function sprite(col){{const s=document.createElement('canvas');s.width=s.height=24;const g=s.getContext('2d');
const r=g.createRadialGradient(12,12,0,12,12,12);r.addColorStop(0,col);r.addColorStop(.25,col+'cc');r.addColorStop(1,col+'00');
g.fillStyle=r;g.fillRect(0,0,24,24);return s}}
function layout(){{const dpr=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;
cells=territories(G.length,W,H,M);
const ga=Math.PI*(3-Math.sqrt(5)),count=G.map(()=>0),maxP=Math.max(...A.map(a=>a[1]));
C=A.map(a=>{{const g=a[3],k=count[g]++;const cell=cells[g],ce=centroid(cell);const R=Math.min(W,H)*.15;
let r=R*Math.sqrt((k+.4)/Math.max(1,A.filter(b=>b[3]===g).length)),x=ce[0]+Math.cos(k*ga)*r,y=ce[1]+Math.sin(k*ga)*r;
for(let t=0;t<12&&!inside(cell,x,y);t++){{x=(x+ce[0])/2;y=(y+ce[1])/2}}
return{{x,y,s:6+Math.sqrt(a[1]/maxP)*30,g}}}});
P=[];A.forEach((a,i)=>{{for(let k=0;k<a[2];k++){{const u=(Math.random()+Math.random()+Math.random()+Math.random())/4-.5;
const rr=Math.abs(u)*2*C[i].s*1.3,t=Math.random()*6.283;
P.push({{a:i,ox:Math.cos(t)*rr,oy:Math.sin(t)*rr,ph:Math.random()*6.283,z:Math.random()<.12}})}}}});
G.forEach(g=>{{if(!sprites[g[1]])sprites[g[1]]=sprite(g[1])}})}}
function draw(time){{const tt=still?0:time/1000,dpr=devicePixelRatio||1,k=view.k;
ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);ctx.setTransform(dpr*k,0,0,dpr*k,dpr*view.x,dpr*view.y);
cells.forEach((cell,i)=>{{if(i===hoverG){{ctx.fillStyle='rgba(255,255,255,.045)';ctx.beginPath();cell.forEach((p,j)=>j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill()}}}});
ctx.globalCompositeOperation='lighter';
for(const p of P){{const c=C[p.a];const x=c.x+p.ox+Math.sin(tt*.35+p.ph)*1.6,y=c.y+p.oy+Math.cos(tt*.3+p.ph*1.3)*1.6;
const col=G[A[p.a][3]][1];ctx.globalAlpha=(hoverA<0||hoverA===p.a)?(hoverG<0||hoverG===A[p.a][3]?.9:.35):.22;
const sz=p.z?9:6;ctx.drawImage(sprites[col],x-sz/2,y-sz/2,sz,sz)}}
ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
drawBorders(ctx,cells,W,H,M,k);
ctx.textAlign='center';ctx.textBaseline='middle';
cells.forEach((cell,i)=>{{const ce=centroid(cell);let lx=ce[0],ly=ce[1]-Math.min(W,H)*.2;if(!inside(cell,lx,ly))ly=ce[1];
ctx.font=`600 ${{19/k}}px Geist Mono, monospace`;ctx.fillStyle=i===hoverG?'#FFFFFF':'rgba(255,255,255,.86)';
ctx.shadowColor='rgba(0,0,0,.6)';ctx.shadowBlur=10;ctx.fillText(G[i][0],lx,ly);ctx.shadowBlur=0;
ctx.font=`${{11.5/k}}px Geist Mono, monospace`;ctx.fillStyle='rgba(255,255,255,.66)';ctx.fillText(G[i][2]+' {escape(labels["plays"])}',lx,ly+20/k)}});
ctx.textAlign='left';ctx.font=`${{11.5/k}}px Geist Mono, monospace`;const shown=G.map(()=>0),limit=k>2.2?99:k>1.4?5:2;
C.forEach((c,i)=>{{if(shown[c.g]<limit||i===hoverA){{shown[c.g]++;const x=c.x+c.s+10/k,y=c.y-c.s*.6;ctx.strokeStyle='rgba(255,255,255,.4)';ctx.lineWidth=1/k;
ctx.beginPath();ctx.moveTo(c.x+c.s*.6,c.y-c.s*.3);ctx.lineTo(x-4/k,y);ctx.stroke();ctx.fillStyle=i===hoverA?'#fff':'rgba(255,255,255,.72)';
ctx.fillText(A[i][0]+'  '+A[i][1],x,y)}}}});
requestAnimationFrame(draw)}}
{ZOOM_JS}
cv.addEventListener('mousemove',e=>{{if(drag){{tip.classList.remove('on');return}}const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;
const[wx,wy]=toWorld(mx,my);hoverG=cells.findIndex(c=>inside(c,wx,wy));let best=-1,bd=1e9;
C.forEach((c,i)=>{{const dd=(c.x-wx)**2+(c.y-wy)**2;if(dd<(c.s+8/view.k)**2&&dd<bd){{bd=dd;best=i}}}});hoverA=best;
if(best>=0){{const a=A[best];tip.innerHTML=(a[4]?`<img src="${{esc(a[4])}}">`:'')+`<div>${{esc(a[0])}}<small>${{esc(G[a[3]][0])}} · ${{a[1]}} {escape(labels["plays"])}</small></div>`;
tip.style.left=Math.min(mx+16,W-280)+'px';tip.style.top=Math.min(my+16,H-80)+'px';tip.classList.add('on')}}else tip.classList.remove('on')}});
cv.addEventListener('mouseleave',()=>{{hoverA=hoverG=-1;tip.classList.remove('on')}});
layout();addEventListener('resize',layout);requestAnimationFrame(draw);
</script></body></html>"""
    st.iframe(html, height=height + 4)


def fingerprint_svg(df: pd.DataFrame, title: str, subtitle: str, size: int = 900, framed: bool = True) -> str:
    """One closed, noise-distorted ring per hour of the day (midnight inside, 23h outside).
    Ring wobble = listening time at that hour; colour = dominant genre at that hour.
    Deterministic for a given dataset, so the same period always gives the same print."""
    cx = cy = size / 2
    top_genres = df["genre"].dropna().value_counts().head(6).index.tolist()
    colors = _palette(top_genres)
    by_hour = df.groupby(df["played_local"].dt.hour)
    minutes = by_hour["minutes"].sum().reindex(range(24), fill_value=0.0)
    dominant = by_hour["genre"].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None)
    mmax = max(float(minutes.max()), 1.0)
    seed = int(df["play_id"].sum()) if "play_id" in df else 7
    rng = random.Random(seed)
    phases = [[rng.uniform(0, 2 * math.pi) for _ in range(5)] for _ in range(24)]
    paths = []
    for h in range(24):
        base = size * 0.07 + h * size * 0.0152
        amp = (minutes[h] / mmax) * size * 0.016 + size * 0.0015
        color = colors.get(dominant.get(h), "#9aa1a9") if minutes[h] > 0 else "#e3e6ea"
        for layer in range(4):  # four fine strokes per ring give the engraved texture
            pts = []
            for k in range(181):
                a = k / 180 * 2 * math.pi
                wob = sum(math.sin(a * (f + 2) + phases[h][f] + layer * .22) / (f + 1.4) for f in range(5)) / 1.6
                r = base + layer * 1.15 + amp * wob
                pts.append(f"{cx + math.cos(a) * r:.1f},{cy + math.sin(a) * r:.1f}")
            paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                         f'stroke-width="{1.0 - layer * .18:.2f}" stroke-opacity="{.92 - layer * .2:.2f}"/>')
    if not framed:  # bare rings, for a page header
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="100%" '
                f'style="max-width:{size}px;display:block;margin:auto">{"".join(paths)}</svg>')
    legend = "".join(
        f'<circle cx="{size - 150}" cy="{46 + i * 19}" r="5" fill="{c}"/>'
        f'<text x="{size - 138}" y="{50 + i * 19}" font-size="13" fill="#4A4843">{escape(str(g))}</text>'
        for i, (g, c) in enumerate(colors.items()))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="100%" '
            f'style="max-width:{size}px;display:block;margin:auto">'
            f'<defs><radialGradient id="fpa" cx="20%" cy="18%" r="80%"><stop offset="0" stop-color="#ddd2ff"/><stop offset="1" stop-color="#ddd2ff" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="fpb" cx="85%" cy="85%" r="75%"><stop offset="0" stop-color="#ffcde0"/><stop offset="1" stop-color="#ffcde0" stop-opacity="0"/></radialGradient></defs>'
            f'<rect width="{size}" height="{size}" rx="36" fill="#f6f3ff"/><rect width="{size}" height="{size}" rx="36" fill="url(#fpa)"/>'
            f'<rect width="{size}" height="{size}" rx="36" fill="url(#fpb)"/>'
            f'<text x="40" y="58" font-family="Geist Mono, ui-monospace, monospace" font-size="34" font-weight="400" letter-spacing="-1" '
            f'fill="#17171A">{escape(title)}</text>'
            f'<text x="40" y="84" font-family="Geist Mono, ui-monospace, monospace" font-size="14" '
            f'fill="#5c6064">{escape(subtitle)}</text>'
            f'<g font-family="Geist Mono, ui-monospace, monospace">{legend}</g>{"".join(paths)}</svg>')
