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

GLOW = ["#8E9CFF", "#FFB08A", "#BBA2FF", "#5FE0B0", "#FFD36B", "#FF9CC6"]  # luminous on the night card
GLOW_OTHER = "#C9C4D8"


def artist_constellation(df: pd.DataFrame, labels: dict, height: int = 680) -> None:
    """Genres are territories (Voronoi cells, labelled); inside, each artist is a glowing
    cloud with one particle per play. The pointer only brushes particles aside.
    labels: {'plays', 'artists', 'other'}."""
    if df.empty:
        return
    genres = df["genre"].dropna().value_counts().head(6).index.tolist()
    gcol = {g: GLOW[i] for i, g in enumerate(genres)}
    d = df.assign(group=df["genre"].where(df["genre"].isin(genres), labels["other"]))
    by_artist = d.groupby("artist_name").agg(plays=("play_id", "count"),
                                             group=("group", lambda s: s.mode().iloc[0]))
    by_artist = by_artist.sort_values("plays", ascending=False).head(48).reset_index()
    groups = [g for g in genres if g in set(by_artist["group"])]
    if labels["other"] in set(by_artist["group"]):
        groups.append(labels["other"])
    weight = by_artist.groupby("group")["plays"].sum()
    total = int(by_artist["plays"].sum())
    scale = min(14.0, 3600 / max(total, 1))
    G = [[escape(str(g)), gcol.get(g, GLOW_OTHER), int(weight.get(g, 0))] for g in groups]
    A = [[escape(str(r.artist_name)), int(r.plays), max(10, int(r.plays * scale)), groups.index(r.group)]
         for r in by_artist.itertuples()]
    caption = f"{total} {labels['plays']} · {len(A)} {labels['artists']}"
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
.night{{position:relative;border-radius:26px;overflow:hidden;background:radial-gradient(120% 90% at 50% 40%,#231C38 0%,#130F1E 60%,#0D0A15 100%)}}
canvas{{display:block;width:100%;height:{height}px}}
.cap{{position:absolute;right:22px;top:20px;font-family:"Geist Mono",monospace;font-size:10.5px;letter-spacing:.16em;
text-transform:uppercase;color:rgba(255,255,255,.55)}}
.tip{{background:#FBFAF8;color:#17171A}}.tip small{{color:#8A8780}}</style></head><body>
<div class="night"><canvas id="c"></canvas><div class="cap">{escape(caption)}</div><div class="tip" id="tip"></div></div>
<script>
const G={json.dumps(G, ensure_ascii=False)}, A={json.dumps(A, ensure_ascii=False)};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
let W,H,seeds=[],cells=[],C=[],P=[],sprites={{}},mouse={{x:-1e4,y:-1e4}},hoverA=-1,hoverG=-1;
function sprite(col){{const s=document.createElement('canvas');s.width=s.height=24;const g=s.getContext('2d');
const r=g.createRadialGradient(12,12,0,12,12,12);r.addColorStop(0,col);r.addColorStop(.25,col+'cc');r.addColorStop(1,col+'00');
g.fillStyle=r;g.fillRect(0,0,24,24);return s}}
function clip(poly,a,b,c){{const out=[];for(let i=0;i<poly.length;i++){{const p=poly[i],q=poly[(i+1)%poly.length];
const fp=a*p[0]+b*p[1]-c,fq=a*q[0]+b*q[1]-c;if(fp<=0)out.push(p);if(fp*fq<0){{const t=fp/(fp-fq);out.push([p[0]+(q[0]-p[0])*t,p[1]+(q[1]-p[1])*t])}}}}return out}}
function inside(poly,x,y){{let k=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){{const[xi,yi]=poly[i],[xj,yj]=poly[j];
if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))k=!k}}return k}}
function centroid(poly){{let x=0,y=0;poly.forEach(p=>{{x+=p[0];y+=p[1]}});return[x/poly.length,y/poly.length]}}
function layout(){{const dpr=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
const n=G.length,cx=W/2,cy=H/2,rx=W*.3,ry=H*.28;
seeds=G.map((g,i)=>n===1?[cx,cy]:[cx+Math.cos(i/n*6.283-1.2)*rx*(i%2?.82:1),cy+Math.sin(i/n*6.283-1.2)*ry*(i%2?.82:1)]);
const m=30,frame=[[m,m],[W-m,m],[W-m,H-m],[m,H-m]];
cells=seeds.map((s,i)=>{{let poly=frame.slice();seeds.forEach((o,j)=>{{if(i===j)return;const a=o[0]-s[0],b=o[1]-s[1];
const c=(o[0]*o[0]+o[1]*o[1]-s[0]*s[0]-s[1]*s[1])/2;poly=clip(poly,a,b,c)}});return poly}});
const ga=Math.PI*(3-Math.sqrt(5)),count=G.map(()=>0),maxP=Math.max(...A.map(a=>a[1]));
C=A.map(a=>{{const g=a[3],k=count[g]++;const cell=cells[g],ce=centroid(cell);const R=Math.min(W,H)*.15;
let r=R*Math.sqrt((k+.4)/Math.max(1,A.filter(b=>b[3]===g).length)),x=ce[0]+Math.cos(k*ga)*r,y=ce[1]+Math.sin(k*ga)*r;
for(let t=0;t<12&&!inside(cell,x,y);t++){{x=(x+ce[0])/2;y=(y+ce[1])/2}}
return{{x,y,s:6+Math.sqrt(a[1]/maxP)*30,g}}}});
P=[];A.forEach((a,i)=>{{for(let k=0;k<a[2];k++){{const u=(Math.random()+Math.random()+Math.random()+Math.random())/4-.5;
const rr=Math.abs(u)*2*C[i].s*1.3,t=Math.random()*6.283;
P.push({{a:i,ox:Math.cos(t)*rr,oy:Math.sin(t)*rr,x:C[i].x+Math.cos(t)*rr,y:C[i].y+Math.sin(t)*rr,vx:0,vy:0,ph:Math.random()*6.283,
z:Math.random()<.12}})}}}});
G.forEach(g=>{{if(!sprites[g[1]])sprites[g[1]]=sprite(g[1])}})}}
function draw(time){{const tt=time/1000;ctx.clearRect(0,0,W,H);
cells.forEach((cell,i)=>{{if(i===hoverG){{ctx.fillStyle='rgba(255,255,255,.045)';ctx.beginPath();cell.forEach((p,k)=>k?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill()}}}});
ctx.globalCompositeOperation='lighter';
for(const p of P){{const c=C[p.a];const tx=c.x+p.ox+Math.sin(tt*.35+p.ph)*2.2,ty=c.y+p.oy+Math.cos(tt*.3+p.ph*1.3)*2.2;
const dx=p.x-mouse.x,dy=p.y-mouse.y,dd=dx*dx+dy*dy;if(dd<2116){{const f=(2116-dd)/2116*.55/Math.sqrt(dd+4);p.vx+=dx*f;p.vy+=dy*f}}
p.vx+=(tx-p.x)*.07;p.vy+=(ty-p.y)*.07;p.vx*=.78;p.vy*=.78;p.x+=p.vx;p.y+=p.vy;
const col=G[A[p.a][3]][1];ctx.globalAlpha=(hoverA<0||hoverA===p.a)?(hoverG<0||hoverG===A[p.a][3]?.9:.35):.25;
const sz=p.z?9:6;ctx.drawImage(sprites[col],p.x-sz/2,p.y-sz/2,sz,sz)}}
ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
ctx.strokeStyle='rgba(255,255,255,.42)';ctx.lineWidth=1.1;const m=30;
cells.forEach(cell=>{{for(let i=0;i<cell.length;i++){{const p=cell[i],q=cell[(i+1)%cell.length];
const onFrame=(Math.abs(p[0]-q[0])<.5&&(Math.abs(p[0]-m)<.5||Math.abs(p[0]-(W-m))<.5))||(Math.abs(p[1]-q[1])<.5&&(Math.abs(p[1]-m)<.5||Math.abs(p[1]-(H-m))<.5));
if(!onFrame){{ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke()}}}}}});
ctx.textAlign='center';ctx.textBaseline='middle';
cells.forEach((cell,i)=>{{const ce=centroid(cell);let lx=ce[0],ly=ce[1]-Math.min(W,H)*.2;if(!inside(cell,lx,ly))ly=ce[1];
ctx.font='500 21px Geist, system-ui, sans-serif';ctx.fillStyle=i===hoverG?'#FFFFFF':'rgba(255,255,255,.86)';
ctx.shadowColor='rgba(0,0,0,.6)';ctx.shadowBlur=10;ctx.fillText(G[i][0],lx,ly);ctx.shadowBlur=0;
ctx.font='10px "Geist Mono", monospace';ctx.fillStyle='rgba(255,255,255,.5)';ctx.fillText((G[i][2]+' {escape(labels["plays"])}').toUpperCase(),lx,ly+20)}});
ctx.textAlign='left';ctx.font='10.5px "Geist Mono", monospace';const shown=G.map(()=>0);
C.forEach((c,i)=>{{if(shown[c.g]<2||i===hoverA){{shown[c.g]++;const x=c.x+c.s+10,y=c.y-c.s*.6;ctx.strokeStyle='rgba(255,255,255,.4)';
ctx.beginPath();ctx.moveTo(c.x+c.s*.6,c.y-c.s*.3);ctx.lineTo(x-4,y);ctx.stroke();ctx.fillStyle=i===hoverA?'#fff':'rgba(255,255,255,.72)';
ctx.fillText(A[i][0].toUpperCase()+'  '+A[i][1],x,y)}}}});
if(!still)requestAnimationFrame(draw)}}
layout();addEventListener('resize',layout);requestAnimationFrame(draw);
cv.addEventListener('mousemove',e=>{{const b=cv.getBoundingClientRect();mouse.x=e.clientX-b.left;mouse.y=e.clientY-b.top;
hoverG=cells.findIndex(c=>inside(c,mouse.x,mouse.y));let best=-1,bd=1e9;
C.forEach((c,i)=>{{const dd=(c.x-mouse.x)**2+(c.y-mouse.y)**2;if(dd<(c.s+8)**2&&dd<bd){{bd=dd;best=i}}}});hoverA=best;
if(best>=0){{tip.innerHTML=`${{A[best][0]}}<small>${{G[A[best][3]][0]}} · ${{A[best][1]}} {escape(labels["plays"])}</small>`;
tip.style.left=Math.min(mouse.x+16,W-270)+'px';tip.style.top=(mouse.y+16)+'px';tip.classList.add('on')}}else tip.classList.remove('on');
if(still)requestAnimationFrame(draw)}});
cv.addEventListener('mouseleave',()=>{{mouse.x=mouse.y=-1e4;hoverA=hoverG=-1;tip.classList.remove('on')}});
</script></body></html>"""
    st.iframe(html, height=height + 4)


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
