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
import streamlit.components.v1 as components

STRONG = ["#6C7FE8", "#EE8E66", "#9B7FD9", "#3FB58E", "#D9A93A", "#E07FA8"]
OTHER = "#B9B5AD"
FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300..600&family=Geist+Mono:wght@400'
         '&display=swap" rel="stylesheet">')
BASE_CSS = """html,body{margin:0;background:transparent;font-family:Geist,system-ui,sans-serif;color:#17171A;
-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;overflow:hidden}
.card{position:relative;background:#FBFAF8;border-radius:26px;overflow:hidden}
.lab{font-family:"Geist Mono",monospace;font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;color:#8A8780}
.legend{position:absolute;left:22px;top:20px;display:flex;flex-direction:column;gap:7px;z-index:2}
.legend span{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#4A4843}
.legend i{width:9px;height:9px;border-radius:9px;display:inline-block}
.tip{position:absolute;pointer-events:none;background:#17171A;color:#fff;padding:9px 12px;border-radius:12px;font-size:12.5px;
line-height:1.35;opacity:0;transform:translateY(4px);transition:opacity .18s,transform .18s cubic-bezier(.22,1,.36,1);max-width:260px;z-index:5}
.tip.on{opacity:1;transform:none}.tip small{color:rgba(255,255,255,.62);display:block}
.corner{position:absolute;right:22px;top:20px;text-align:right;z-index:2}"""


def _palette(labels: list[str]) -> dict[str, str]:
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
ctx.fillStyle='#8A8780';ctx.font='10.5px "Geist Mono", monospace';ctx.textAlign='center';ctx.textBaseline='middle';
H.forEach((h,i)=>{{const a=i/H.length*Math.PI*2-Math.PI/2;ctx.fillText(h.toUpperCase(),cx+Math.cos(a)*(R1+24),cy+Math.sin(a)*(R1+24))}})}}
let shown=still?P.length:0,hover=-1;
function draw(){{ctx.clearRect(0,0,W,Hh);guide();
for(let i=0;i<shown;i++){{const[x,y,r]=pos[i];ctx.globalAlpha=i===hover?1:.82;ctx.fillStyle=P[i][3];ctx.beginPath();ctx.arc(x,y,i===hover?r+2.5:r,0,7);ctx.fill()}}
ctx.globalAlpha=1;if(hover>=0){{const[x,y,r]=pos[hover];ctx.strokeStyle='#17171A';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,r+6,0,7);ctx.stroke()}}}}
fit();addEventListener('resize',()=>{{fit();draw()}});
const t0=performance.now();function anim(n){{shown=Math.min(P.length,Math.floor(P.length*Math.min(1,(n-t0)/1800)**.7));draw();if(shown<P.length)requestAnimationFrame(anim)}}
still?draw():requestAnimationFrame(anim);
cv.addEventListener('mousemove',e=>{{const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;let best=-1,bd=196;
pos.forEach((p,i)=>{{const dd=(p[0]-mx)**2+(p[1]-my)**2;if(dd<bd){{bd=dd;best=i}}}});
if(best!==hover){{hover=best;draw()}}if(best>=0){{const p=P[best];tip.innerHTML=`${{p[4]}}<small>${{p[5]}} · ${{p[2].toFixed(1)}} min</small>`;
tip.style.left=Math.min(mx+14,W-270)+'px';tip.style.top=(my+14)+'px';tip.classList.add('on')}}else tip.classList.remove('on')}});
cv.addEventListener('mouseleave',()=>{{hover=-1;tip.classList.remove('on');draw()}});
</script></body></html>"""
    components.html(html, height=height + 4)


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
    components.html(html, height=height + 4)


# --- 3. artist constellation ------------------------------------------------------------------

def artist_constellation(df: pd.DataFrame, plays_label: str, other_label: str, height: int = 640) -> None:
    if df.empty:
        return
    g = df.groupby("artist_name").agg(plays=("play_id", "count"), genre=("genre", lambda s: s.dropna().mode().iloc[0]
                                                                          if s.notna().any() else None))
    g = g.sort_values("plays", ascending=False).head(28).reset_index()
    colors = _palette(df["genre"].dropna().value_counts().head(6).index.tolist())
    total = int(g["plays"].sum())
    scale = min(12.0, 3200 / max(total, 1))  # ~3,200 particles whatever the volume
    data = [[escape(str(r.artist_name)), int(r.plays), max(12, int(r.plays * scale)), colors.get(r.genre, OTHER)]
            for r in g.itertuples()]
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
canvas{{display:block;width:100%;height:{height}px}}</style></head><body><div class="card">
{_legend(colors, other_label)}<canvas id="c"></canvas><div class="tip" id="tip"></div></div>
<script>
const A={json.dumps(data, ensure_ascii=False)};const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;let W,H,C=[],parts=[],mouse={{x:-999,y:-999}},hover=-1;
function layout(){{const d=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*d;cv.height=H*d;ctx.setTransform(d,0,0,d,0,0);
const ga=Math.PI*(3-Math.sqrt(5)),R=Math.min(W*.44,H*.42),maxP=A[0][1];
C=A.map((a,i)=>{{const r=R*Math.sqrt((i+.5)/A.length);const ang=i*ga-0.6;return{{x:W/2+Math.cos(ang)*r*1.35,y:H/2+Math.sin(ang)*r,s:9+Math.sqrt(a[1]/maxP)*34}}}});
parts=[];A.forEach((a,i)=>{{for(let k=0;k<a[2];k++){{const g=(Math.random()+Math.random()+Math.random())/3;const rr=Math.abs(g-.5)*2*C[i].s*1.15,t=Math.random()*7;
parts.push({{c:i,ox:Math.cos(t)*rr,oy:Math.sin(t)*rr,x:C[i].x+Math.cos(t)*rr*4,y:C[i].y+Math.sin(t)*rr*4,vx:0,vy:0,ph:Math.random()*7}})}}}})}}
layout();addEventListener('resize',layout);
function step(time){{const tt=time/1000;ctx.clearRect(0,0,W,H);
for(const p of parts){{const c=C[p.c];const tx=c.x+p.ox+Math.sin(tt*.6+p.ph)*3,ty=c.y+p.oy+Math.cos(tt*.5+p.ph*1.3)*3;
let dx=p.x-mouse.x,dy=p.y-mouse.y,dd=dx*dx+dy*dy;if(dd<6400){{const f=(6400-dd)/6400*1.6/Math.sqrt(dd+1);p.vx+=dx*f;p.vy+=dy*f}}
p.vx+=(tx-p.x)*.02;p.vy+=(ty-p.y)*.02;p.vx*=.86;p.vy*=.86;p.x+=p.vx;p.y+=p.vy;
ctx.globalAlpha=hover<0||hover===p.c?.78:.16;ctx.fillStyle=A[p.c][3];ctx.beginPath();ctx.arc(p.x,p.y,1.35,0,6.3);ctx.fill()}}
ctx.globalAlpha=1;ctx.font='10.5px "Geist Mono", monospace';ctx.textBaseline='middle';
C.forEach((c,i)=>{{if(i<6||i===hover){{const x=c.x+c.s+8,y=c.y-c.s*.55;ctx.strokeStyle='rgba(23,23,26,.55)';ctx.lineWidth=1;
ctx.beginPath();ctx.moveTo(c.x+c.s*.7,c.y-c.s*.35);ctx.lineTo(x-3,y);ctx.stroke();ctx.fillStyle=i===hover?'#17171A':'rgba(23,23,26,.72)';
ctx.fillText((A[i][0]+'  '+A[i][1]).toUpperCase(),x,y)}}}});if(!still)requestAnimationFrame(step)}}
requestAnimationFrame(step);
cv.addEventListener('mousemove',e=>{{const b=cv.getBoundingClientRect();mouse.x=e.clientX-b.left;mouse.y=e.clientY-b.top;
let best=-1;C.forEach((c,i)=>{{if((c.x-mouse.x)**2+(c.y-mouse.y)**2<(c.s+10)**2)best=i}});hover=best;
if(best>=0){{tip.innerHTML=`${{A[best][0]}}<small>${{A[best][1]}} {escape(plays_label)}</small>`;tip.style.left=Math.min(mouse.x+14,W-270)+'px';
tip.style.top=(mouse.y+14)+'px';tip.classList.add('on')}}else tip.classList.remove('on');if(still)requestAnimationFrame(step)}});
cv.addEventListener('mouseleave',()=>{{mouse.x=mouse.y=-999;hover=-1;tip.classList.remove('on')}});
</script></body></html>"""
    components.html(html, height=height + 4)


# --- 4. generative fingerprint -----------------------------------------------------------------

def fingerprint_svg(df: pd.DataFrame, title: str, subtitle: str, size: int = 900) -> str:
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
        color = colors.get(dominant.get(h), OTHER) if minutes[h] > 0 else "#D9D6CF"
        for layer in range(4):  # four fine strokes per ring give the engraved texture
            pts = []
            for k in range(181):
                a = k / 180 * 2 * math.pi
                wob = sum(math.sin(a * (f + 2) + phases[h][f] + layer * .22) / (f + 1.4) for f in range(5)) / 1.6
                r = base + layer * 1.15 + amp * wob
                pts.append(f"{cx + math.cos(a) * r:.1f},{cy + math.sin(a) * r:.1f}")
            paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
                         f'stroke-width="{1.0 - layer * .18:.2f}" stroke-opacity="{.92 - layer * .2:.2f}"/>')
    legend = "".join(
        f'<circle cx="{size - 150}" cy="{46 + i * 19}" r="5" fill="{c}"/>'
        f'<text x="{size - 138}" y="{50 + i * 19}" font-size="13" fill="#4A4843">{escape(str(g))}</text>'
        for i, (g, c) in enumerate(colors.items()))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="100%" '
            f'style="max-width:{size}px;display:block;margin:auto">'
            f'<rect width="{size}" height="{size}" rx="28" fill="#FBFAF8"/>'
            f'<text x="40" y="58" font-family="Geist, system-ui, sans-serif" font-size="30" letter-spacing="-1" '
            f'fill="#17171A">{escape(title)}</text>'
            f'<text x="40" y="84" font-family="Geist Mono, monospace" font-size="11" letter-spacing="2" '
            f'fill="#8A8780">{escape(subtitle.upper())}</text>'
            f'<g font-family="Geist, system-ui, sans-serif">{legend}</g>{"".join(paths)}</svg>')
