"""Interactive pieces rendered in their own frame: the genre wheel (D3), the map of
recommendations, and the recommendation cards with 30 s previews.

Shared JavaScript:
- ZOOM_JS: wheel / pinch zoom around the pointer, drag to pan, double-click or button to reset.
- PLAYER_JS: plays a Deezer preview fetched at click time (preview links expire after ~15 min;
  api.deezer.com answers JSONP, so the browser can ask it directly), one preview at a time
  across every frame of the page.
"""

from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

FONT_LINK = ('<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@300..700&display=swap" '
             'rel="stylesheet">')
FONT = "'Geist Mono', ui-monospace, Menlo, monospace"
ENGINE_COLORS = {"neighbours": "#ff7a59", "genres": "#38b6ff", "moment": "#a98bff"}

ZOOM_CSS = """
.zoom{position:absolute;right:16px;bottom:16px;display:flex;gap:6px;z-index:6}
.zoom button{width:34px;height:34px;border-radius:50%;border:1.5px solid rgba(255,255,255,.55);background:rgba(20,20,34,.55);
 color:#fff;font:500 16px/1 FONT;cursor:pointer;backdrop-filter:blur(6px)}
.zoom button:hover{background:rgba(255,255,255,.18)}
.hint{position:absolute;left:18px;bottom:20px;font:12px FONT;color:rgba(255,255,255,.55);z-index:6;pointer-events:none}
@media (max-width:640px){.hint{display:none}}
""".replace("FONT", FONT)

ZOOM_HTML = '<div class="zoom"><button id="zin" title="+">+</button><button id="zout" title="−">−</button><button id="zreset" title="⟲">⟲</button></div>'

ZOOM_JS = """
const view={k:1,x:0,y:0};let drag=null,moved=false,pinch=null;
function clampView(){const mx=W*(window.EDGE||0),my=H*(window.EDGE||0);view.x=Math.min(mx,Math.max(W-W*view.k-mx,view.x));view.y=Math.min(my,Math.max(H-H*view.k-my,view.y))}
function zoomAt(mx,my,f){const k=Math.min(window.KMAX||8,Math.max(1,view.k*f));view.x=mx-(mx-view.x)*k/view.k;view.y=my-(my-view.y)*k/view.k;view.k=k;clampView()}
function resetView(){view.k=1;view.x=0;view.y=0}
function toWorld(mx,my){return[(mx-view.x)/view.k,(my-view.y)/view.k]}
cv.style.cursor='grab';
cv.addEventListener('wheel',e=>{e.preventDefault();const b=cv.getBoundingClientRect();zoomAt(e.clientX-b.left,e.clientY-b.top,Math.exp(-e.deltaY*.0016))},{passive:false});
cv.addEventListener('mousedown',e=>{drag=[e.clientX,e.clientY];moved=false;cv.style.cursor='grabbing'});
addEventListener('mouseup',()=>{drag=null;cv.style.cursor='grab'});
addEventListener('mousemove',e=>{if(!drag)return;const dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(Math.abs(dx)+Math.abs(dy)>2)moved=true;
 view.x+=dx;view.y+=dy;drag=[e.clientX,e.clientY];clampView()});
cv.addEventListener('dblclick',resetView);
document.getElementById('zin').onclick=()=>zoomAt(W/2,H/2,1.6);
document.getElementById('zout').onclick=()=>zoomAt(W/2,H/2,1/1.6);
document.getElementById('zreset').onclick=resetView;
cv.addEventListener('touchstart',e=>{if(e.touches.length===2){const[a,b]=e.touches;pinch=Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY)}
 else drag=[e.touches[0].clientX,e.touches[0].clientY];moved=false},{passive:true});
cv.addEventListener('touchmove',e=>{e.preventDefault();const r=cv.getBoundingClientRect();
 if(e.touches.length===2&&pinch){const[a,b]=e.touches;const d=Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);
  zoomAt((a.clientX+b.clientX)/2-r.left,(a.clientY+b.clientY)/2-r.top,d/pinch);pinch=d}
 else if(drag){const t=e.touches[0];view.x+=t.clientX-drag[0];view.y+=t.clientY-drag[1];drag=[t.clientX,t.clientY];moved=true;clampView()}},{passive:false});
cv.addEventListener('touchend',()=>{drag=null;pinch=null});
"""

# Voronoi territories of the genres (shared by the constellation and the map of recommendations).
TERRITORY_JS = """
function clip(poly,a,b,c){const out=[];for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length];
 const fp=a*p[0]+b*p[1]-c,fq=a*q[0]+b*q[1]-c;if(fp<=0)out.push(p);if(fp*fq<0){const t=fp/(fp-fq);out.push([p[0]+(q[0]-p[0])*t,p[1]+(q[1]-p[1])*t])}}return out}
function inside(poly,x,y){let k=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const[xi,yi]=poly[i],[xj,yj]=poly[j];
 if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))k=!k}return k}
function centroid(poly){let x=0,y=0;poly.forEach(p=>{x+=p[0];y+=p[1]});return[x/poly.length,y/poly.length]}
function territories(n,W,H,m){const cx=W/2,cy=H/2,rx=W*.3,ry=H*.28;
 const seeds=Array.from({length:n},(_,i)=>n===1?[cx,cy]:[cx+Math.cos(i/n*6.283-1.2)*rx*(i%2?.82:1),cy+Math.sin(i/n*6.283-1.2)*ry*(i%2?.82:1)]);
 const frame=[[m,m],[W-m,m],[W-m,H-m],[m,H-m]];
 return seeds.map((s,i)=>{let poly=frame.slice();seeds.forEach((o,j)=>{if(i===j)return;const a=o[0]-s[0],b=o[1]-s[1];
  const c=(o[0]*o[0]+o[1]*o[1]-s[0]*s[0]-s[1]*s[1])/2;poly=clip(poly,a,b,c)});return poly})}
function drawBorders(ctx,cells,W,H,m,k){ctx.strokeStyle='rgba(255,255,255,.35)';ctx.lineWidth=1.1/k;
 cells.forEach(cell=>{for(let i=0;i<cell.length;i++){const p=cell[i],q=cell[(i+1)%cell.length];
  const onFrame=(Math.abs(p[0]-q[0])<.5&&(Math.abs(p[0]-m)<.5||Math.abs(p[0]-(W-m))<.5))||(Math.abs(p[1]-q[1])<.5&&(Math.abs(p[1]-m)<.5||Math.abs(p[1]-(H-m))<.5));
  if(!onFrame){ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke()}}})}
"""

PLAYER_JS = """
const audio=new Audio();audio.preload='none';let playing=null;const ME=Math.random().toString(36).slice(2);let bc=null;
function stopHere(){audio.pause();playing=null;setPlaying(null)}
try{bc=new BroadcastChannel('ds-preview');bc.onmessage=m=>{if(m.data!==ME&&playing!==null)stopHere()}}catch(e){}
function jsonp(url){return new Promise((res,rej)=>{const cb='dz'+Math.random().toString(36).slice(2);const s=document.createElement('script');
 const t=setTimeout(()=>{delete window[cb];s.remove();rej('timeout')},9000);
 window[cb]=d=>{clearTimeout(t);delete window[cb];s.remove();res(d)};s.onerror=()=>{clearTimeout(t);rej('error')};
 s.src=url+(url.includes('?')?'&':'?')+'output=jsonp&callback='+cb;document.head.appendChild(s)})}
async function toggle(id){if(playing===id){stopHere();return}
 audio.pause();playing=id;setPlaying(id,'loading');
 try{const d=await jsonp('https://api.deezer.com/track/'+id);if(playing!==id)return;if(!d||!d.preview)throw 'none';
  audio.src=d.preview;await audio.play();if(playing!==id)return;setPlaying(id);if(bc)bc.postMessage(ME)}
 catch(e){if(playing===id){playing=null;setPlaying(null);noPreview(id)}}}
audio.addEventListener('ended',()=>{playing=null;setPlaying(null)});
"""


ESC_JS = "const esc=s=>String(s).replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"


def js_data(value) -> str:
    """JSON for a <script> block: raw strings (canvas draws them as is), never closing the tag."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _frame(html: str, height: int) -> None:
    st.iframe(html, height=height)


# --- the genre wheel ----------------------------------------------------------------------------

def genre_wheel(frame: pd.DataFrame, colors: dict[str, str], labels: dict, height: int = 600) -> None:
    """Genres → artists → albums as a zoomable wheel (D3). frame columns: genre, artist, picture,
    album, cover, minutes. Click a genre or an artist to dive in, click the centre to come back;
    hovering shows the photo or the cover in the centre."""
    if frame.empty:
        return
    tree = {"name": labels["root"], "children": []}
    for genre, g in frame.groupby("genre", sort=False):
        artists = []
        for artist, a in g.groupby("artist", sort=False):
            albums = [{"name": str(r.album), "img": r.cover if isinstance(r.cover, str) else "", "value": round(float(r.minutes), 2)}
                      for r in a.sort_values("minutes", ascending=False).head(4).itertuples(index=False)]
            pic = a["picture"].dropna()
            artists.append({"name": str(artist), "img": pic.iloc[0] if len(pic) else "", "children": albums})
        tree["children"].append({"name": str(genre), "color": colors.get(genre, "#c4c9d0"), "children": artists})
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>html,body{{margin:0;background:transparent;font-family:{FONT};color:#1f1f1f;overflow:hidden;-webkit-font-smoothing:antialiased}}
.wrap{{position:relative;height:{height - 8}px;border-radius:22px;background:rgba(255,255,255,.42)}}
svg{{display:block;width:100%;height:100%}}
.arc{{cursor:pointer;transition:opacity .25s}}
.lab{{font-size:11px;font-weight:550;letter-spacing:-.02em;pointer-events:none;fill:#1f1f1f}}
.c-name{{font-size:17px;font-weight:600;letter-spacing:-.05em}} .c-val{{font-size:13px;font-weight:450}} .c-share{{font-size:11px;fill:rgba(31,31,31,.6)}}
.hint{{position:absolute;left:18px;top:14px;font-size:11px;color:rgba(31,31,31,.55)}}</style></head><body>
<div class="wrap"><svg id="w"></svg><div class="hint">{escape(labels["hint"])}</div></div>
<script>
const data={js_data(tree)};
const svg=d3.select('#w');const box=document.querySelector('.wrap');
const W=box.clientWidth,H=box.clientHeight,S=Math.min(W,H)-24,radius=S/6;
svg.attr('viewBox',[-W/2,-H/2,W,H]);
const fmt=m=>m>=60?Math.floor(m/60)+' h '+String(Math.round(m%60)).padStart(2,'0'):Math.round(m)+' min';
const mix=(c,t)=>d3.interpolateRgb(c,'#ffffff')(t);
const root=d3.partition().size([2*Math.PI,4])(d3.hierarchy(data).sum(d=>d.value||0).sort((a,b)=>b.value-a.value));
root.each(d=>{{d.current=d;const g=d.depth===1?d:d.ancestors().find(a=>a.depth===1);
 d.color=d.depth===0?'#fff':d.depth===1?d.data.color:mix(g.data.color,d.depth===2?.18+.42*(d.parent.children.indexOf(d)/Math.max(1,d.parent.children.length)):.55+.25*(d.parent.children.indexOf(d)/Math.max(1,d.parent.children.length)))}});
const arc=d3.arc().startAngle(d=>d.x0).endAngle(d=>d.x1).padAngle(d=>Math.min((d.x1-d.x0)/2,.012)).padRadius(radius*1.5)
 .innerRadius(d=>d.y0*radius+2).outerRadius(d=>Math.max(d.y0*radius+2,d.y1*radius-2)).cornerRadius(7);
const defs=svg.append('defs');
const g=svg.append('g');
const shadow=defs.append('filter').attr('id','sh').attr('x','-20%').attr('y','-20%').attr('width','140%').attr('height','140%');
shadow.append('feDropShadow').attr('dx',0).attr('dy',6).attr('stdDeviation',8).attr('flood-color','#283060').attr('flood-opacity',.18);
const path=g.append('g').attr('filter','url(#sh)').selectAll('path').data(root.descendants().slice(1)).join('path')
 .attr('class','arc').attr('fill',d=>d.color).attr('stroke','#fff').attr('stroke-width',1.5)
 .attr('fill-opacity',d=>visible(d.current)?1:0).attr('stroke-opacity',d=>visible(d.current)?1:0)
 .attr('pointer-events',d=>visible(d.current)?'auto':'none').attr('d',d=>arc(d.current));
// artwork on the arcs that are wide enough
const pics=g.append('g').selectAll('g').data(root.descendants().filter(d=>d.depth>=2&&d.data.img)).join('g').attr('pointer-events','none');
pics.each(function(d,i){{const id='cp'+i;defs.append('clipPath').attr('id',id).append('circle').attr('r',15);
 d3.select(this).append('circle').attr('r',16.5).attr('fill','#fff');
 d3.select(this).append('image').attr('href',d.data.img).attr('x',-15).attr('y',-15).attr('width',30).attr('height',30)
  .attr('clip-path',`url(#${{id}})`).attr('preserveAspectRatio','xMidYMid slice')}});
const label=g.append('g').attr('text-anchor','middle').selectAll('text').data(root.descendants().slice(1)).join('text')
 .attr('class','lab').attr('dy','0.35em').attr('fill-opacity',d=>+labelVisible(d.current)).attr('transform',d=>labelTransform(d.current))
 .text(d=>labelText(d,d.current));
function labelText(d,c){{const room=Math.floor((radius-(picVisible(c)?46:16))/6.9),n=d.data.name;return n.length>room?n.slice(0,Math.max(3,room-1))+'…':n}}
// centre: white disc with the focus or the hovered item, its artwork and its time
const centre=svg.append('g').style('cursor','pointer').on('click',(e)=>clicked(e,focus.parent||root));
centre.append('circle').attr('r',radius-6).attr('fill','#fff').attr('stroke','rgba(255,255,255,.9)').attr('stroke-width',3).attr('filter','url(#sh)');
const ri=radius*.3,icy=-radius*.32;
defs.append('clipPath').attr('id','cimg').append('circle').attr('cx',0).attr('cy',icy).attr('r',ri);
const cimg=centre.append('image').attr('x',-ri).attr('y',icy-ri).attr('width',ri*2).attr('height',ri*2)
 .attr('clip-path','url(#cimg)').attr('preserveAspectRatio','xMidYMid slice');
const cname=centre.append('text').attr('class','c-name').attr('text-anchor','middle'),cval=centre.append('text').attr('class','c-val').attr('text-anchor','middle'),
 cshare=centre.append('text').attr('class','c-share').attr('text-anchor','middle');
let focus=root;
function show(d){{const img=d.depth>=2?d.data.img:'';cimg.attr('href',img||null).style('display',img?null:'none');
 const top=img?radius*.12:-radius*.12;const n=d.data.name,room=Math.floor(radius*1.6/10.5);cname.attr('y',top+8).text(n.length>room?n.slice(0,room-1)+'…':n);
 cval.attr('y',top+28).text(fmt(d.value));
 cshare.attr('y',top+46).text(d.parent?Math.round(100*d.value/d.parent.value)+' % · '+(d.parent.depth?d.parent.data.name:{json.dumps(labels["total"])}):{json.dumps(labels["click"])})}}
show(root);
path.on('mouseenter',(e,d)=>{{show(d);path.attr('opacity',p=>p===d||d.ancestors().includes(p)||p.ancestors().includes(d)?1:.45)}})
 .on('mouseleave',()=>{{show(focus);path.attr('opacity',1)}})
 .filter(d=>d.children).style('cursor','pointer').on('click',clicked);
function clicked(event,p){{focus=p;show(p);
 root.each(d=>d.target={{x0:Math.max(0,Math.min(1,(d.x0-p.x0)/(p.x1-p.x0)))*2*Math.PI,x1:Math.max(0,Math.min(1,(d.x1-p.x0)/(p.x1-p.x0)))*2*Math.PI,
  y0:Math.max(0,d.y0-p.depth),y1:Math.max(0,d.y1-p.depth)}});
 const t=svg.transition().duration(event&&event.altKey?3000:700).ease(d3.easeCubicInOut);
 path.transition(t).tween('data',d=>{{const i=d3.interpolate(d.current,d.target);return t=>d.current=i(t)}})
  .filter(function(d){{return +this.getAttribute('fill-opacity')||visible(d.target)}})
  .attr('fill-opacity',d=>visible(d.target)?1:0).attr('stroke-opacity',d=>visible(d.target)?1:0)
  .attr('pointer-events',d=>visible(d.target)?'auto':'none').attrTween('d',d=>()=>arc(d.current));
 label.filter(function(d){{return +this.getAttribute('fill-opacity')||labelVisible(d.target)}}).transition(t)
  .attr('fill-opacity',d=>+labelVisible(d.target)).attrTween('transform',d=>()=>labelTransform(d.current));
 label.text(d=>labelText(d,d.target));
 pics.transition(t).attrTween('transform',d=>()=>picTransform(d.current)).attr('opacity',d=>+picVisible(d.target))}}
function visible(d){{return d.y1<=3&&d.y0>=1&&d.x1>d.x0}}
function labelVisible(d){{return d.y1<=3&&d.y0>=1&&(d.y1-d.y0)*(d.x1-d.x0)>.05}}
function picVisible(d){{return d.y1<=3&&d.y0>=2&&(d.x1-d.x0)*(d.y0+.5)*radius>40}}
function labelTransform(d){{const x=(d.x0+d.x1)/2*180/Math.PI,y=(d.y0+d.y1)/2*radius+(picVisible(d)?-20:0);
 return `rotate(${{x-90}}) translate(${{y}},0) rotate(${{x<180?0:180}})`}}
function picTransform(d){{const a=(d.x0+d.x1)/2,r=d.y1*radius-22;return `translate(${{Math.sin(a)*r}},${{-Math.cos(a)*r}})`}}
pics.attr('transform',d=>picTransform(d.current)).attr('opacity',d=>+picVisible(d.current));
</script></body></html>"""
    _frame(html, height)


# --- the map of recommendations ---------------------------------------------------------------------

def rec_map(seeds: list[dict], recs: list[dict], genres: list[tuple[str, str]], labels: dict, height: int = 640) -> None:
    """Your artists and what is recommended from them, on the map of your genres.
    seeds: {id, name, genre, minutes, img}; recs: {track_id, title, artist, engine, genre, seed, img, reason};
    genres: (name, colour). Click a recommendation to hear it."""
    gi = {g: i for i, (g, _) in enumerate(genres)}
    S = [[s["name"], gi.get(s["genre"], len(genres) - 1), float(s["minutes"]), s["img"] or "", int(s["id"])] for s in seeds]
    sid = {s[4]: i for i, s in enumerate(S)}
    R = [[r["title"], r["artist"], r["engine"], gi.get(r["genre"], len(genres) - 1),
          sid.get(r["seed"], -1), r["img"] or "", int(r["track_id"]), r["reason"] or ""] for r in recs]
    G = [[g, c] for g, c in genres]
    present = {r["engine"] for r in recs}
    legend = "".join(f"<span><i style='border-color:{ENGINE_COLORS[e]}'></i>{escape(labels[e])}</span>"
                     for e in ENGINE_COLORS if e in present)
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}<style>
html,body{{margin:0;background:transparent;font-family:{FONT};-webkit-font-smoothing:antialiased;overflow:hidden}}
.night{{position:relative;border-radius:22px;overflow:hidden;background:radial-gradient(120% 90% at 50% 40%,#231C38 0%,#130F1E 60%,#0D0A15 100%)}}
canvas{{display:block;width:100%;height:{height - 44}px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12px;color:rgba(255,255,255,.82);padding:14px 18px 4px}}
.legend span{{display:flex;align-items:center;gap:7px}}.legend i{{width:12px;height:12px;border-radius:50%;border:2.5px solid;display:inline-block}}
.legend i.me{{border-color:#fff;background:#fff}}
.tip{{position:absolute;pointer-events:none;display:flex;gap:12px;align-items:center;background:#fbfaf8;color:#17171a;padding:10px 14px 10px 10px;
 border-radius:16px;font-size:12px;line-height:1.4;opacity:0;transform:translateY(4px);transition:opacity .15s,transform .15s;max-width:320px;z-index:7}}
.tip.on{{opacity:1;transform:none}}.tip img{{width:52px;height:52px;border-radius:10px;object-fit:cover}}.tip b{{display:block;font-size:13px}}
.tip small{{display:block;color:#6b6f73}}.tip em{{display:block;font-style:normal;font-weight:600;margin-top:2px}}
{ZOOM_CSS}</style></head><body>
<div class="night"><div class="legend"><span><i class="me"></i>{escape(labels["you"])}</span>{legend}</div><canvas id="c"></canvas>
<div class="tip" id="tip"></div>{ZOOM_HTML}<div class="hint">{escape(labels["hint"])}</div></div>
<script>
const G={js_data(G)},S={js_data(S)},R={js_data(R)};{ESC_JS}
const EC={json.dumps(ENGINE_COLORS)},L={json.dumps({k: labels[k] for k in ("play", "pause", "because", "no_preview", "loading")}, ensure_ascii=False)};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');let W=0,H=0;
{TERRITORY_JS}
const imgs={{}};function img(u){{if(!u)return null;if(!imgs[u]){{const i=new Image();i.src=u;imgs[u]=i}}return imgs[u]}}
let cells=[],N=[],hover=-1,state={{}};const M=30,RR=R.length>120?8.5:R.length>60?10.5:13;
function layout(){{const dpr=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;
 cells=territories(G.length,W,H,M);const maxM=Math.max(...S.map(s=>s[2]),1);N=[];
 const per=G.map(()=>0),tot=G.map((_,g)=>S.filter(s=>s[1]===g).length),ga=Math.PI*(3-Math.sqrt(5));
 S.forEach((s,i)=>{{const c=centroid(cells[s[1]]),k=per[s[1]]++;const r=Math.min(W,H)*.1*Math.sqrt((k+.3)/Math.max(1,tot[s[1]]));
  N.push({{kind:'s',i,x:c[0]+Math.cos(k*ga)*r,y:c[1]+Math.sin(k*ga)*r,r:16+14*Math.sqrt(s[2]/maxM),g:s[1],img:s[3]}})}});
 const around={{}};R.forEach((r,i)=>{{const anchor=r[4]>=0?N[r[4]]:null;const key=r[4]>=0?'s'+r[4]:'g'+r[3];const k=around[key]=(around[key]||0)+1;
  const base=anchor?[anchor.x,anchor.y]:centroid(cells[r[3]]);const a=k*2.4+(anchor?anchor.i:r[3]),d=(anchor?anchor.r:24)+40+12*Math.floor(k/6);
  N.push({{kind:'r',i,x:base[0]+Math.cos(a)*d,y:base[1]+Math.sin(a)*d,r:RR,g:r[3],img:r[5],anchor}})}});
 for(let it=0;it<140;it++){{for(let a=0;a<N.length;a++)for(let b=a+1;b<N.length;b++){{const p=N[a],q=N[b];let dx=q.x-p.x,dy=q.y-p.y;
  const d=Math.hypot(dx,dy)||.01,min=p.r+q.r+10;if(d<min){{const f=(min-d)/2/d;dx*=f;dy*=f;if(p.kind==='r'||q.kind==='s'){{p.x-=dx;p.y-=dy}}if(q.kind==='r'||p.kind==='s'){{q.x+=dx;q.y+=dy}}}}}}
  N.forEach(n=>{{const cell=cells[n.g];if(!inside(cell,n.x,n.y)){{const c=centroid(cell);n.x+=(c[0]-n.x)*.08;n.y+=(c[1]-n.y)*.08}}
   if(n.anchor){{const dx=n.x-n.anchor.x,dy=n.y-n.anchor.y,d=Math.hypot(dx,dy);if(d>140){{n.x-=dx*.04;n.y-=dy*.04}}}}}})}}}}
function disc(n,ring,width,k){{const im=img(n.img);ctx.save();ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.closePath();
 if(im&&im.complete&&im.naturalWidth){{ctx.clip();ctx.drawImage(im,n.x-n.r,n.y-n.r,n.r*2,n.r*2)}}else{{ctx.fillStyle='#3a3550';ctx.fill()}}ctx.restore();
 ctx.beginPath();ctx.arc(n.x,n.y,n.r+width/2,0,6.283);ctx.strokeStyle=ring;ctx.lineWidth=width;ctx.stroke()}}
function draw(t){{const dpr=devicePixelRatio||1,k=view.k;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
 ctx.setTransform(dpr*k,0,0,dpr*k,dpr*view.x,dpr*view.y);
 cells.forEach((cell,i)=>{{ctx.fillStyle=G[i][1]+'14';ctx.beginPath();cell.forEach((p,j)=>j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fill()}});
 drawBorders(ctx,cells,W,H,M,k);
 ctx.textAlign='center';ctx.textBaseline='middle';
 cells.forEach((cell,i)=>{{const c=centroid(cell);let ly=c[1]-Math.min(W,H)*.2;if(!inside(cell,c[0],ly))ly=c[1]-60;
  ctx.font=`600 ${{18/k}}px Geist Mono, monospace`;ctx.fillStyle=G[i][1];ctx.shadowColor='rgba(0,0,0,.7)';ctx.shadowBlur=8;ctx.fillText(G[i][0],c[0],ly);ctx.shadowBlur=0}});
 N.forEach(n=>{{if(n.kind!=='r'||!n.anchor)return;const r=R[n.i];const on=hover===N.indexOf(n)||state.id===r[6];
  ctx.strokeStyle=EC[r[2]]+(on?'ee':'70');ctx.lineWidth=(on?2.4:1.3)/k;ctx.setLineDash(r[2]==='moment'?[4/k,4/k]:[]);
  const mx=(n.x+n.anchor.x)/2+(n.anchor.y-n.y)*.18,my=(n.y+n.anchor.y)/2+(n.x-n.anchor.x)*.18;
  ctx.beginPath();ctx.moveTo(n.anchor.x,n.anchor.y);ctx.quadraticCurveTo(mx,my,n.x,n.y);ctx.stroke()}});ctx.setLineDash([]);
 N.forEach((n,j)=>{{if(n.kind==='s'){{disc(n,'#ffffff',3,k);
   if(k>1.25||n.r>22){{ctx.font=`${{11/k}}px Geist Mono, monospace`;ctx.fillStyle='rgba(255,255,255,.85)';ctx.fillText(S[n.i][0],n.x,n.y+n.r+12/k)}}}}
  else{{const r=R[n.i],playing=state.id===r[6];const pulse=playing?1+.15*Math.sin(t/180):1;
   if(playing||hover===j){{ctx.beginPath();ctx.arc(n.x,n.y,(n.r+7)*pulse,0,6.283);ctx.fillStyle=EC[r[2]]+'44';ctx.fill()}}
   disc(n,EC[r[2]],3,k);
   if(playing||hover===j){{ctx.fillStyle='rgba(0,0,0,.45)';ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fill();ctx.fillStyle='#fff';
    if(playing&&state.s!=='loading'){{ctx.fillRect(n.x-4,n.y-5,3,10);ctx.fillRect(n.x+1,n.y-5,3,10)}}else{{ctx.beginPath();ctx.moveTo(n.x-3,n.y-6);ctx.lineTo(n.x+6,n.y);ctx.lineTo(n.x-3,n.y+6);ctx.fill()}}}}
   if(k>1.8){{ctx.font=`${{10/k}}px Geist Mono, monospace`;ctx.fillStyle='rgba(255,255,255,.75)';ctx.fillText(r[0].length>18?r[0].slice(0,17)+'…':r[0],n.x,n.y+n.r+11/k)}}}}}});
 requestAnimationFrame(draw)}}
{ZOOM_JS}
{PLAYER_JS}
function setPlaying(id,s){{state={{id,s}}}}
function noPreview(id){{const n=N.find(n=>n.kind==='r'&&R[n.i][6]===id);if(n){{tip.innerHTML='<div><b>'+esc(R[n.i][0])+'</b><small>'+esc(L.no_preview)+'</small></div>';tip.classList.add('on')}}}}
function pick(mx,my){{const[x,y]=toWorld(mx,my);let best=-1,bd=1e9;N.forEach((n,j)=>{{const d=(n.x-x)**2+(n.y-y)**2;if(d<(n.r+4/view.k)**2&&d<bd){{bd=d;best=j}}}});return best}}
cv.addEventListener('mousemove',e=>{{if(drag)return;const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;hover=pick(mx,my);
 if(hover<0){{tip.classList.remove('on');cv.style.cursor='grab';return}}const n=N[hover];cv.style.cursor=n.kind==='r'?'pointer':'grab';
 if(n.kind==='s'){{const s=S[n.i];tip.innerHTML=(s[3]?'<img src="'+esc(s[3])+'">':'')+'<div><b>'+esc(s[0])+'</b><small>'+esc(G[s[1]][0])+'</small></div>'}}
 else{{const r=R[n.i];tip.innerHTML=(r[5]?'<img src="'+esc(r[5])+'">':'')+'<div><b>'+esc(r[0])+'</b><small>'+esc(r[1])+'</small><em style="color:'+EC[r[2]]+'">'+esc(L.because[r[2]]||'')+' '+esc(r[7])+'</em><small>'+esc(state.id===r[6]?L.pause:L.play)+'</small></div>'}}
 tip.style.left=Math.min(mx+18,W-330)+'px';tip.style.top=Math.min(my+18,H-90)+'px';tip.classList.add('on')}});
cv.addEventListener('mouseleave',()=>{{hover=-1;tip.classList.remove('on')}});
cv.addEventListener('click',e=>{{if(moved)return;const b=cv.getBoundingClientRect(),j=pick(e.clientX-b.left,e.clientY-b.top);if(j>=0&&N[j].kind==='r')toggle(R[N[j].i][6])}});
layout();addEventListener('resize',layout);requestAnimationFrame(draw);
</script></body></html>"""
    _frame(html, height)


# --- the table of recommendations ------------------------------------------------------------------

def _table_css(color: str, height: int) -> str:
    """The look shared by the track tables: a frosted panel, a filter bar, sticky headers, covers
    that play their preview."""
    return f"""html,body{{margin:0;background:transparent;font-family:{FONT};color:#1f1f1f;-webkit-font-smoothing:antialiased}}
.wrap{{height:{height - 8}px;display:flex;flex-direction:column;background:rgba(255,255,255,.72);border-radius:22px;overflow:hidden}}
.bar{{display:flex;align-items:center;gap:14px;padding:12px 16px;border-bottom:1px solid rgba(31,31,31,.07)}}
.bar input{{flex:1;max-width:360px;font:500 13px {FONT};padding:9px 16px;border-radius:999px;border:1.5px solid rgba(31,31,31,.12);
 background:#fff;outline:none}} .bar input:focus{{border-color:{color}}}
.bar span{{font-size:12px;color:rgba(31,31,31,.6)}}
.scroll{{overflow:auto;flex:1}}
table{{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}}
th{{position:sticky;top:0;z-index:2;background:rgba(250,250,252,.96);backdrop-filter:blur(6px);text-align:left;font-weight:600;
 font-size:11.5px;letter-spacing:.02em;color:rgba(31,31,31,.6);padding:10px 8px;cursor:pointer;white-space:nowrap;user-select:none}}
th:hover{{color:#1f1f1f}} th.on{{color:#1f1f1f}} th.on::after{{content:' ↓'}} th.on.asc::after{{content:' ↑'}}
td{{padding:6px 8px;border-top:1px solid rgba(31,31,31,.05);vertical-align:middle}}
tr:hover td{{background:rgba(255,255,255,.75)}} tr.playing td{{background:{color}1f}}
.n{{width:30px;color:rgba(31,31,31,.45);text-align:right;font-variant-numeric:tabular-nums}}
.cov{{position:relative;width:48px;height:48px;border-radius:12px;overflow:hidden;cursor:pointer;background:#e9e9ee;flex:none}}
.cov img{{width:100%;height:100%;object-fit:cover;display:block}}
.cov .b{{position:absolute;inset:0;display:grid;place-items:center;background:rgba(17,17,17,.0);transition:background .2s}}
.cov .b svg{{width:18px;height:18px;fill:#fff;opacity:0;transition:opacity .2s;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))}}
tr:hover .cov .b{{background:rgba(17,17,17,.35)}} tr:hover .cov .b svg, tr.playing .cov .b svg{{opacity:1}}
tr.playing .cov .b{{background:{color}cc}}
.cov i{{position:absolute;left:0;bottom:0;height:3px;background:#fff;width:0}}
.t{{font-weight:600;letter-spacing:-.02em;max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.a,.al{{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}} .al{{color:rgba(31,31,31,.62)}}
.w{{max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:rgba(31,31,31,.7)}} .w b{{color:#1f1f1f;font-weight:600}}
.g{{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-size:12px}} .g i{{width:9px;height:9px;border-radius:50%;display:inline-block}}
.d{{color:rgba(31,31,31,.55);font-variant-numeric:tabular-nums;white-space:nowrap}}
.l a{{color:#0b57d0;text-decoration:none;font-size:12px;white-space:nowrap}}
tr.none .cov{{opacity:.45}}"""


def rec_table(recs: pd.DataFrame, labels: dict, color: str, genre_colors: dict[str, str], height: int | None = None) -> None:
    """Every recommended track in one table: play its 30 s preview from the row, sort by any
    column, filter as you type; the playing row shows its progress."""
    rows = [[i + 1, int(r.track_id), str(r.title), str(r.artist_name), str(r.album_title or ""), str(r.reason or ""),
             str(r.genre or ""), int(r.duration or 0), r.cover or "", r.link, genre_colors.get(r.genre, "#c4c9d0")]
            for i, r in enumerate(recs.itertuples(index=False))]
    height = height or min(118 + 62 * len(rows), 860)
    L = {k: labels[k] for k in ("title", "artist", "album", "why", "genre", "time", "search", "count", "because",
                                "open", "no_preview", "play")}
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}<style>
{_table_css(color, height)}
@media (max-width:1100px){{.al,th:nth-child(5){{display:none}}}}
@media (max-width:720px){{.al,.w,.g,.d,th:nth-child(5),th:nth-child(6),th:nth-child(7),th:nth-child(8){{display:none}}}}
</style></head><body><div class="wrap"><div class="bar"><input id="q" placeholder="{escape(L['search'])}"><span id="cnt"></span></div>
<div class="scroll"><table><thead><tr><th data-k="0">#</th><th></th><th data-k="2">{escape(L['title'])}</th><th data-k="3">{escape(L['artist'])}</th>
<th data-k="4">{escape(L['album'])}</th><th data-k="5">{escape(L['why'])}</th><th data-k="6">{escape(L['genre'])}</th><th data-k="7">{escape(L['time'])}</th><th></th></tr></thead>
<tbody id="tb"></tbody></table></div></div>
<script>
const D={js_data(rows)},L={js_data(L)};{ESC_JS}
const PLAY='<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',PAUSE='<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>',
 WAIT='<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>';
let sortK=0,asc=true,q='';const fmt=s=>s?Math.floor(s/60)+':'+String(s%60).padStart(2,'0'):'–';
function render(){{let rows=D.filter(r=>!q||(r[2]+' '+r[3]+' '+r[4]+' '+r[5]+' '+r[6]).toLowerCase().includes(q));
 rows.sort((a,b)=>{{const x=a[sortK],y=b[sortK];const c=typeof x==='number'?x-y:String(x).localeCompare(String(y));return asc?c:-c}});
 document.getElementById('cnt').textContent=L.count.replace('{{n}}',rows.length);
 document.getElementById('tb').innerHTML=rows.map(r=>`<tr data-id="${{r[1]}}" class="${{playing===r[1]?'playing':''}}"><td class="n">${{r[0]}}</td>
 <td><div class="cov" title="${{esc(L.play)}}">${{r[8]?`<img src="${{esc(r[8])}}" loading="lazy" alt="">`:''}}<div class="b">${{playing===r[1]?PAUSE:PLAY}}</div><i></i></div></td>
 <td class="t" title="${{esc(r[2])}}">${{esc(r[2])}}</td><td class="a" title="${{esc(r[3])}}">${{esc(r[3])}}</td><td class="al" title="${{esc(r[4])}}">${{esc(r[4])}}</td>
 <td class="w" title="${{esc(L.because+' '+r[5])}}">${{esc(L.because)}} <b>${{esc(r[5])}}</b></td>
 <td><span class="g"><i style="background:${{r[10]}}"></i>${{esc(r[6])}}</span></td><td class="d">${{fmt(r[7])}}</td>
 <td class="l"><a href="${{esc(r[9])}}" target="_blank" rel="noopener">${{esc(L.open)}} ↗</a></td></tr>`).join('');
 document.querySelectorAll('.cov').forEach(c=>c.addEventListener('click',()=>toggle(+c.closest('tr').dataset.id)));
 document.querySelectorAll('th').forEach(h=>h.classList.toggle('on',+h.dataset.k===sortK&&h.dataset.k!==undefined));
 document.querySelectorAll('th.on').forEach(h=>h.classList.toggle('asc',asc))}}
document.querySelectorAll('th[data-k]').forEach(h=>h.addEventListener('click',()=>{{const k=+h.dataset.k;asc=sortK===k?!asc:true;sortK=k;render()}}));
document.getElementById('q').addEventListener('input',e=>{{q=e.target.value.toLowerCase().trim();render()}});
{PLAYER_JS}
function setPlaying(id,s){{document.querySelectorAll('tbody tr').forEach(tr=>{{const on=+tr.dataset.id===id;tr.classList.toggle('playing',on);
 tr.querySelector('.b').innerHTML=on?(s==='loading'?WAIT:PAUSE):PLAY;if(!on)tr.querySelector('.cov i').style.width=0}})}}
function noPreview(id){{const tr=document.querySelector(`tr[data-id="${{id}}"]`);if(tr){{tr.classList.add('none');tr.querySelector('.cov').title=L.no_preview}}}}
audio.addEventListener('timeupdate',()=>{{const i=document.querySelector(`tr[data-id="${{playing}}"] .cov i`);if(i&&audio.duration)i.style.width=(100*audio.currentTime/audio.duration)+'%'}});
render();
</script></body></html>"""
    _frame(html, height)


def insta_table(rows: list[dict], labels: dict, color: str, source_colors: dict[str, str], height: int | None = None) -> None:
    """The playlist of an Instagram account: newest post first, each track with its post (date and
    link), where it was found (with the words it came from) and its 30 s preview; sort by any
    column, filter as you type.
    rows: {track_id, title, artist, album, kind, at (ISO), date, source, line, post, link, cover, posts}"""
    data = [[i + 1, int(r["track_id"]), r["title"], r["artist"], r["album"], r["at"], r["date"], r["source"], r["line"],
             r["post"], r["link"], r["cover"], r["kind"], int(r["posts"])] for i, r in enumerate(rows)]
    height = height or min(118 + 62 * len(data), 860)
    L = {k: labels[k] for k in ("title", "artist", "album", "posted", "found", "search", "count", "open", "post", "no_preview",
                                "play", "album_badge", "sources", "times")}
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}<style>
{_table_css(color, height)}
.badge{{display:inline-block;font-size:10px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:1px 6px;border-radius:999px;
 background:rgba(31,31,31,.08);color:rgba(31,31,31,.7);margin-left:6px;vertical-align:1px}}
.dt{{white-space:nowrap;font-variant-numeric:tabular-nums}} .dt small{{display:block;font-size:11px;color:rgba(31,31,31,.5)}}
.src{{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-size:12px;max-width:230px}}
.src i{{width:9px;height:9px;border-radius:50%;flex:none}} .src span{{overflow:hidden;text-overflow:ellipsis;color:rgba(31,31,31,.62)}}
.src b{{font-weight:600}}
.l a.ig{{color:#c13584}}
@media (max-width:1100px){{.al,th:nth-child(5){{display:none}}}}
@media (max-width:720px){{.al,.src,.l.dz,th:nth-child(5),th:nth-child(7),th:nth-child(9){{display:none}}}}
</style></head><body><div class="wrap"><div class="bar"><input id="q" placeholder="{escape(L['search'])}"><span id="cnt"></span></div>
<div class="scroll"><table><thead><tr><th data-k="0">#</th><th></th><th data-k="2">{escape(L['title'])}</th><th data-k="3">{escape(L['artist'])}</th>
<th data-k="4">{escape(L['album'])}</th><th data-k="5">{escape(L['posted'])}</th><th data-k="7">{escape(L['found'])}</th><th></th><th></th></tr></thead>
<tbody id="tb"></tbody></table></div></div>
<script>
const D={js_data(data)},L={js_data(L)},SC={js_data(source_colors)};{ESC_JS}
const PLAY='<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',PAUSE='<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>',
 WAIT='<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>';
let sortK=5,asc=false,q='';
function render(){{let rows=D.filter(r=>!q||(r[2]+' '+r[3]+' '+r[4]+' '+r[6]+' '+r[8]).toLowerCase().includes(q));
 rows.sort((a,b)=>{{const x=a[sortK],y=b[sortK];const c=typeof x==='number'?x-y:String(x).localeCompare(String(y));return asc?c:-c}});
 document.getElementById('cnt').textContent=L.count.replace('{{n}}',rows.length);
 document.getElementById('tb').innerHTML=rows.map(r=>`<tr data-id="${{r[1]}}" class="${{playing===r[1]?'playing':''}}"><td class="n">${{r[0]}}</td>
 <td><div class="cov" title="${{esc(L.play)}}">${{r[11]?`<img src="${{esc(r[11])}}" loading="lazy" alt="">`:''}}<div class="b">${{playing===r[1]?PAUSE:PLAY}}</div><i></i></div></td>
 <td class="t" title="${{esc(r[2])}}">${{esc(r[2])}}${{r[12]==='album'?`<span class="badge">${{esc(L.album_badge)}}</span>`:''}}</td>
 <td class="a" title="${{esc(r[3])}}">${{esc(r[3])}}</td><td class="al" title="${{esc(r[4])}}">${{esc(r[4])}}</td>
 <td class="dt">${{esc(r[6])}}${{r[13]>1?`<small>${{esc(L.times.replace('{{n}}',r[13]))}}</small>`:''}}</td>
 <td><span class="src" title="${{esc(r[8])}}"><i style="background:${{SC[r[7]]||'#c4c9d0'}}"></i><b>${{esc(L.sources[r[7]]||r[7])}}</b>${{r[8]?`<span>· ${{esc(r[8])}}</span>`:''}}</span></td>
 <td class="l"><a class="ig" href="${{esc(r[9])}}" target="_blank" rel="noopener">${{esc(L.post)}} ↗</a></td>
 <td class="l dz"><a href="${{esc(r[10])}}" target="_blank" rel="noopener">${{esc(L.open)}} ↗</a></td></tr>`).join('');
 document.querySelectorAll('.cov').forEach(c=>c.addEventListener('click',()=>toggle(+c.closest('tr').dataset.id)));
 document.querySelectorAll('th').forEach(h=>h.classList.toggle('on',+h.dataset.k===sortK&&h.dataset.k!==undefined));
 document.querySelectorAll('th.on').forEach(h=>h.classList.toggle('asc',asc))}}
document.querySelectorAll('th[data-k]').forEach(h=>h.addEventListener('click',()=>{{const k=+h.dataset.k;asc=sortK===k?!asc:k!==5;sortK=k;render()}}));
document.getElementById('q').addEventListener('input',e=>{{q=e.target.value.toLowerCase().trim();render()}});
{PLAYER_JS}
function setPlaying(id,s){{document.querySelectorAll('tbody tr').forEach(tr=>{{const on=+tr.dataset.id===id;tr.classList.toggle('playing',on);
 tr.querySelector('.b').innerHTML=on?(s==='loading'?WAIT:PAUSE):PLAY;if(!on)tr.querySelector('.cov i').style.width=0}})}}
function noPreview(id){{const tr=document.querySelector(`tr[data-id="${{id}}"]`);if(tr){{tr.classList.add('none');tr.querySelector('.cov').title=L.no_preview}}}}
audio.addEventListener('timeupdate',()=>{{const i=document.querySelector(`tr[data-id="${{playing}}"] .cov i`);if(i&&audio.duration)i.style.width=(100*audio.currentTime/audio.duration)+'%'}});
render();
</script></body></html>"""
    _frame(html, height)


# --- the map of sound ------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _genre_table() -> str:
    """The 6,300 genres of the map and their nested regions, as compact JSON for the page."""
    from core import soundmap

    data = json.loads((Path(__file__).resolve().parents[1] / "assets" / "genre_map.json").read_text(encoding="utf-8"))
    g = data["genres"]
    levels = soundmap.hierarchy()["levels"]
    return js_data({"n": [r[0] for r in g], "c": [r[1] for r in g], "x": [r[2] for r in g], "y": [r[3] for r in g],
                    "s": [r[5] for r in g], "levels": levels})


def sound_map(mine: list[dict], recs: list[dict], paths: list[tuple[str, str]], labels: dict, color: str,
              height: int = 780) -> None:
    """The map of sound, in the manner of a research-space map: the 6,291 genres of Every Noise at
    Once as a nebula (density in magma colours), cut into nested regions whose names appear and
    fade as you zoom (families, then smaller families, then every sub-genre). Each sub-genre is a
    cloud of points, denser when the genre is popular, in the hue of its family (a shade per smaller
    family), that shows as you zoom while the nebula dims.
    Your tracks (white) and the discoveries (the mode's colour) are clouds of points around their
    sub-genre that turn into album covers when you zoom in; click a discovery to hear it.
    mine: {title, artist, img, x, y}; recs: {title, artist, img, track_id, reason, x, y, subgenre};
    x, y in 0..1; paths: (from genre, to genre) for the sub-genres mode."""
    legend = (f"<span><b class='neb'></b>{escape(labels['density'])}</span>"
              f"<span><b class='dust'></b>{escape(labels['clouds'])}</span>"
              f"<span><i class='me'></i>{escape(labels['mine'])}</span>"
              f"<span><i style='background:{color};box-shadow:0 0 8px {color}'></i>{escape(labels['found'])}</span>")
    html = f"""<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}<style>
html,body{{margin:0;background:transparent;font-family:{FONT};-webkit-font-smoothing:antialiased;overflow:hidden}}
.space{{position:relative;border-radius:22px;overflow:hidden;background:#090a18}}
.top{{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;padding:12px 16px 6px;font-size:12px;color:rgba(255,255,255,.82)}}
.top span{{display:flex;align-items:center;gap:7px}}
.top i{{width:9px;height:9px;border-radius:50%;display:inline-block}} .top i.me{{background:#fff;box-shadow:0 0 8px #fff}}
.top b.neb{{width:34px;height:10px;border-radius:5px;background:linear-gradient(90deg,#2a0f5c,#812581,#e55964,#fec287,#fcfdbf)}}
.top b.dust{{width:26px;height:10px;background:radial-gradient(circle,#ff8fb1 1.4px,transparent 1.8px) 0 0/7px 6px,
 radial-gradient(circle,#7fd6ff 1.4px,transparent 1.8px) 3px 3px/7px 6px,radial-gradient(circle,#ffd36e 1.2px,transparent 1.6px) 5px 1px/9px 5px}}
.top input{{margin-left:auto;font:500 12px {FONT};padding:7px 14px;border-radius:999px;border:1.5px solid rgba(255,255,255,.28);
 background:rgba(255,255,255,.08);color:#fff;outline:none;width:240px}} .top input::placeholder{{color:rgba(255,255,255,.5)}}
.chips{{display:flex;gap:6px;overflow-x:auto;padding:4px 16px 8px;scrollbar-width:none}} .chips::-webkit-scrollbar{{display:none}}
.chips button{{flex:none;font:500 11.5px {FONT};color:#fff;background:rgba(255,255,255,.07);border:1.5px solid rgba(255,255,255,.22);
 border-radius:999px;padding:5px 11px;cursor:pointer;white-space:nowrap}} .chips button b{{color:{color};margin-left:6px;font-weight:600}}
.chips button:hover,.chips button.on{{background:rgba(255,255,255,.18);border-color:{color}}}
canvas{{display:block;width:100%;height:{height - 92}px}}
.tip{{position:absolute;pointer-events:none;display:flex;gap:12px;align-items:center;background:rgba(14,15,34,.92);color:#fff;padding:10px 14px 10px 10px;
 border:1px solid rgba(255,255,255,.18);border-radius:14px;font-size:12px;line-height:1.45;opacity:0;transform:translateY(4px);
 transition:opacity .15s,transform .15s;max-width:340px;z-index:7;backdrop-filter:blur(8px)}}
.tip.on{{opacity:1;transform:none}}.tip img{{width:56px;height:56px;border-radius:10px;object-fit:cover}}.tip b{{display:block;font-size:13px}}
.tip small{{display:block;color:rgba(255,255,255,.62)}}.tip em{{display:block;font-style:normal;font-weight:600;margin-top:2px}}
{ZOOM_CSS}</style></head><body>
<div class="space"><div class="top">{legend}<input id="find" list="gl" placeholder="{escape(labels['search'])}"><datalist id="gl"></datalist></div>
<div class="chips" id="chips"></div><canvas id="c"></canvas><div class="tip" id="tip"></div>
<div class="zoom"><button id="zfit" title="{escape(labels['fit'])}">◎</button><button id="zin">+</button><button id="zout">−</button><button id="zreset" title="{escape(labels['whole'])}">⟲</button></div>
<div class="hint">{escape(labels['hint'])}</div></div>
<script>
window.KMAX=80;window.EDGE=.06;
const GM={_genre_table()},U={js_data(mine)},R={js_data(recs)},P={js_data(paths)},MC={js_data(color)};
const L={js_data({k: labels[k] for k in ("play", "pause", "no_preview", "because", "yours", "in", "count")})};
{ESC_JS}
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');let W=0,H=0,dirty=true;
const N=GM.n.length,idx={{}};GM.n.forEach((n,i)=>idx[n]=i);const L1=GM.levels[0],L2=GM.levels[1];
const cap=s=>s?s.charAt(0).toUpperCase()+s.slice(1):s;
document.getElementById('gl').innerHTML=GM.n.map(n=>'<option value="'+esc(n)+'">').join('');
const explored=new Set();R.forEach(r=>{{if(r.subgenre&&idx[r.subgenre]!==undefined)explored.add(idx[r.subgenre])}});
const pathIdx=P.map(([a,b])=>[idx[a],idx[b]]).filter(([a,b])=>a!==undefined&&b!==undefined);
// clouds: each point is scattered around its sub-genre, the same way every time
const hash=i=>{{let h=(i+1)*2654435761>>>0;h^=h>>>15;h=Math.imul(h,2246822519)>>>0;h^=h>>>13;return (h>>>0)/4294967296}};
const scatter=(arr,seed,sigma)=>arr.forEach((p,i)=>{{const u=Math.max(1e-6,hash(seed+i*2)),v=hash(seed+i*2+1),r=sigma*Math.sqrt(-2*Math.log(u));
 p.px=p.x+Math.cos(6.283*v)*r/1.6;p.py=p.y+Math.sin(6.283*v)*r}});
scatter(U,11,.0042);scatter(R,977,.0048);
// each sub-genre's own cloud, in the hue of its family (14 hues placed so that neighbouring families
// never look alike) with a shade per smaller family; more points and a wider spread when the genre
// is popular; a share of the points shows at first, all of them once zoomed in
const FH=(()=>{{const n=L1.names.length,hues=[],free=[...Array(n).keys()].map(i=>i*360/n),d=(a,b)=>Math.hypot((L1.cx[a]-L1.cx[b])*1.6,L1.cy[a]-L1.cy[b]);
 [...Array(n).keys()].sort((a,b)=>L1.cy[a]-L1.cy[b]||L1.cx[a]-L1.cx[b]).forEach(a=>{{let best=0,bs=-1;
  free.forEach((h,fi)=>{{let sc=1e9;hues.forEach((hb,b)=>{{if(hb===undefined)return;const hd=Math.min(Math.abs(h-hb),360-Math.abs(h-hb));sc=Math.min(sc,hd+300*Math.max(0,d(a,b)-.15))}});if(sc>bs){{bs=sc;best=fi}}}});
  hues[a]=free.splice(best,1)[0]}});return hues}})();
const GC=GM.n.map((_,i)=>{{const f=L1.of[i],s=L2.of[i]%4;return `hsl(${{Math.round(FH[f]+(s-1.5)*7)}},${{86-s*4}}%,${{60+s*5}}%)`}});
const DO=new Int32Array(N+1),DSIG=new Float32Array(N);for(let i=0;i<N;i++){{const c=Math.round(5+40/Math.sqrt(1+i/25));DO[i+1]=DO[i]+c;DSIG[i]=.0018+.0028*(c-5)/40}}
const DX=new Float32Array(DO[N]),DY=new Float32Array(DO[N]);
for(let i=0;i<N;i++)for(let j=DO[i];j<DO[i+1];j++){{const u=Math.max(1e-6,hash(j*2+31)),v=hash(j*2+32),r=DSIG[i]*Math.sqrt(-2*Math.log(u));
 DX[j]=GM.x[i]+Math.cos(6.283*v)*r/1.6;DY[j]=GM.y[i]+Math.sin(6.283*v)*r}}
const imgs={{}};function img(u){{if(!u)return null;if(!imgs[u]){{const i=new Image();i.onload=()=>dirty=true;i.src=u;imgs[u]=i}}return imgs[u]}}
// the nebula: points splatted in grey on a small canvas, then coloured with the magma scale
const STOPS=[[0,[9,10,24]],[.12,[28,16,68]],[.25,[79,18,123]],[.4,[129,37,129]],[.55,[181,54,122]],[.68,[229,89,100]],[.8,[251,135,97]],[.9,[254,194,135]],[1,[252,253,191]]];
const LUT=new Uint8ClampedArray(256*4);for(let i=0;i<256;i++){{const t=i/255;let a=STOPS[0],b=STOPS[STOPS.length-1];
 for(let j=0;j<STOPS.length-1;j++)if(t>=STOPS[j][0]&&t<=STOPS[j+1][0]){{a=STOPS[j];b=STOPS[j+1];break}}
 const f=(t-a[0])/Math.max(1e-6,b[0]-a[0]);for(let c=0;c<3;c++)LUT[i*4+c]=a[1][c]+(b[1][c]-a[1][c])*f;LUT[i*4+3]=Math.min(235,Math.pow(t,.75)*330)}}
const sprite=(()=>{{const s=document.createElement('canvas');s.width=s.height=64;const g=s.getContext('2d');const r=g.createRadialGradient(32,32,0,32,32,32);
 r.addColorStop(0,'rgba(255,255,255,1)');r.addColorStop(.35,'rgba(255,255,255,.45)');r.addColorStop(1,'rgba(255,255,255,0)');g.fillStyle=r;g.fillRect(0,0,64,64);return s}})();
const dc=document.createElement('canvas'),dctx=dc.getContext('2d',{{willReadFrequently:true}}),cc=document.createElement('canvas'),cctx=cc.getContext('2d');
let cells1=[],cells2=[];
{TERRITORY_JS}
function voronoi(L){{const pts=L.cx.map((x,j)=>[x*W,L.cy[j]*H]),frame=[[-W,-H],[2*W,-H],[2*W,2*H],[-W,2*H]];
 return pts.map((s,i)=>{{let poly=frame.slice();pts.forEach((o,j)=>{{if(i===j)return;const a=o[0]-s[0],b=o[1]-s[1],c=(o[0]*o[0]+o[1]*o[1]-s[0]*s[0]-s[1]*s[1])/2;poly=clip(poly,a,b,c)}});return poly}})}}
function layout(){{const dpr=devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;
 dc.width=cc.width=Math.ceil(W/4);dc.height=cc.height=Math.ceil(H/4);cells1=voronoi(L1);cells2=voronoi(L2);dirty=true}}
const sx=x=>x*W*view.k+view.x,sy=y=>y*H*view.k+view.y;
// density in floating point (no saturation): a gaussian per point, popular genres and your
// tracks weigh more, then an automatic exposure (99.2nd percentile) and the magma scale
const ramp=(k,a,b)=>Math.max(0,Math.min(1,(k-a)/(b-a)));
let G=null;const GWT=new Float32Array(N);for(let i=0;i<N;i++)GWT[i]=.25+4/Math.sqrt(i+4);
function nebula(){{const k=view.k,q=1/4,w=dc.width,h=dc.height;if(!G||G.length!==w*h)G=new Float32Array(w*h);else G.fill(0);
 const R=Math.max(1.3,11*Math.pow(k,.5)*q),s2=2*(R*.55)**2,rad=Math.ceil(R*1.5),K=[];
 for(let dy=-rad;dy<=rad;dy++)for(let dx=-rad;dx<=rad;dx++){{const v=Math.exp(-(dx*dx+dy*dy)/s2);if(v>.03)K.push(dx+dy*w,dx,dy,v)}}
 const splat=(x,y,wt)=>{{const cx=Math.round(x),cy=Math.round(y);if(cx<-rad||cy<-rad||cx>=w+rad||cy>=h+rad)return;const base=cy*w+cx;
  for(let j=0;j<K.length;j+=4){{const X=cx+K[j+1],Y=cy+K[j+2];if(X<0||Y<0||X>=w||Y>=h)continue;G[base+K[j]]+=K[j+3]*wt}}}};
 for(let i=0;i<N;i++)splat(sx(GM.x[i])*q,sy(GM.y[i])*q,GWT[i]);
 for(const p of U)splat(sx(p.px)*q,sy(p.py)*q,.35);
 const sample=[];for(let p=0;p<G.length;p+=5)if(G[p]>0)sample.push(G[p]);sample.sort((a,b)=>a-b);
 const top=sample.length?sample[Math.floor(sample.length*.992)]:1;
 const out=cctx.createImageData(w,h),o=out.data;for(let p=0,j=0;p<G.length;p++,j+=4){{const v=G[p];if(v<=0)continue;
  const t=Math.min(255,Math.round(Math.pow(v/top,1.15)*255))*4;o[j]=LUT[t];o[j+1]=LUT[t+1];o[j+2]=LUT[t+2];o[j+3]=LUT[t+3]}}
 cctx.putImageData(out,0,0);ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.globalAlpha=1-.5*ramp(k,3,12);ctx.drawImage(cc,0,0,W,H);ctx.globalAlpha=1}}
function dust(){{const k=view.k,share=.18+.82*ramp(k,1,3.2),r=Math.min(4.6,1.1+k*.22),h=r/2,round=k>=5;ctx.globalAlpha=.35+.55*ramp(k,1.2,4);
 for(let i=0;i<N;i++){{const x=sx(GM.x[i]),y=sy(GM.y[i]),m=DSIG[i]*4*W*k;if(x<-m||y<-m*1.6||x>W+m||y>H+m*1.6)continue;
  const end=DO[i]+Math.max(1,Math.round((DO[i+1]-DO[i])*share));ctx.fillStyle=GC[i];ctx.beginPath();
  for(let j=DO[i];j<end;j++){{const px=sx(DX[j]),py=sy(DY[j]);if(round){{ctx.moveTo(px+h,py);ctx.arc(px,py,h,0,6.283)}}else ctx.rect(px-h,py-h,r,r)}}ctx.fill()}}
 ctx.globalAlpha=1}}
function borders(cells,alpha,width){{if(alpha<=0)return;const k=view.k;ctx.save();ctx.setTransform((devicePixelRatio||1)*k,0,0,(devicePixelRatio||1)*k,(devicePixelRatio||1)*view.x,(devicePixelRatio||1)*view.y);
 ctx.strokeStyle=`rgba(214,224,255,${{alpha}})`;ctx.lineWidth=width/k;cells.forEach(c=>{{ctx.beginPath();c.forEach((p,j)=>j?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.stroke()}});ctx.restore()}}
let nodes=[],labelsDrawn=[],hover=null,fly=null,pulse=null,state={{}};
function draw(t){{const dpr=devicePixelRatio||1,k=view.k;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#090a18';ctx.fillRect(0,0,W,H);
 nebula();dust();
 borders(cells1,.5*(1-ramp(k,6,14)),1.3);borders(cells2,.24*ramp(k,1.2,1.8)*(1-ramp(k,20,40)),1);
 // stars: every sub-genre, brighter when popular
 for(let i=0;i<N;i++){{const x=sx(GM.x[i]),y=sy(GM.y[i]);if(x<0||y<0||x>W||y>H)continue;const r=(.55+(GM.s[i]-100)/60*.9)*Math.min(2.2,.8+k*.06);
  ctx.fillStyle=explored.has(i)?MC:`rgba(255,255,255,${{.35+.5*Math.max(0,1-i/N)}})`;ctx.fillRect(x-r/2,y-r/2,r,r)}}
 // discovery paths
 pathIdx.forEach(([a,b])=>{{const x1=sx(GM.x[a]),y1=sy(GM.y[a]),x2=sx(GM.x[b]),y2=sy(GM.y[b]),mx=(x1+x2)/2+(y2-y1)*.2,my=(y1+y2)/2-(x2-x1)*.2;
  ctx.strokeStyle=MC;ctx.globalAlpha=.55;ctx.lineWidth=1.2;ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(x1,y1);ctx.quadraticCurveTo(mx,my,x2,y2);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1}});
 // labels: families, then smaller families, then every sub-genre, never overlapping
 const cell=10,grid=new Set();labelsDrawn=[];
 const put=(text,x,y,fs,weight,fill,alpha,force,info)=>{{if(alpha<=.03||x<-80||y<-20||x>W+80||y>H+20)return;const w=text.length*fs*.6,x0=x-w/2,y0=y-fs/2,cs=[];
  for(let cx=Math.floor(x0/cell);cx<=Math.floor((x0+w)/cell);cx++)for(let cy=Math.floor(y0/cell);cy<=Math.floor((y0+fs)/cell);cy++)cs.push(cx+','+cy);
  if(!force&&cs.some(c=>grid.has(c)))return;cs.forEach(c=>grid.add(c));ctx.globalAlpha=alpha;ctx.font=`${{weight}} ${{fs}}px Geist Mono, monospace`;
  ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineJoin='round';ctx.strokeStyle='rgba(9,10,24,.85)';ctx.lineWidth=Math.max(3,fs*.28);ctx.strokeText(text,x,y);
  ctx.fillStyle=fill;ctx.fillText(text,x,y);ctx.globalAlpha=1;labelsDrawn.push([info,x0,y0,w,fs])}};
 const a1=1-ramp(k,2.4,4.2),a2=ramp(k,1.25,1.9)*(1-ramp(k,14,26)),a3=ramp(k,2.8,4.2);
 if(pulse!==null)put(cap(GM.n[pulse]),sx(GM.x[pulse]),sy(GM.y[pulse])-10,14,700,'#ffffff',1,true,['g',pulse]);
 L1.names.forEach((n,j)=>put(n,sx(L1.cx[j]),sy(L1.cy[j]),22,650,'#ffffff',a1,false,['l1',j]));
 L2.names.forEach((n,j)=>put(n,sx(L2.cx[j]),sy(L2.cy[j]),14,560,'#d9e2ff',a2*.95,false,['l2',j]));
 explored.forEach(i=>put(GM.n[i],sx(GM.x[i]),sy(GM.y[i])-9,12,650,MC,Math.max(a3,.85*ramp(k,1.5,2.5)),false,['g',i]));
 if(a3>0){{const limit=Math.min(N,Math.round(40*Math.pow(k,1.75)));for(let i=0;i<limit;i++)put(GM.n[i],sx(GM.x[i]),sy(GM.y[i])-8,11,450,'rgba(236,238,255,.92)',a3*.9,false,['g',i])}}
 // your tracks and the discoveries: glowing points, album covers once close enough
 const covers=k>=5,rc=7+Math.min(10,Math.max(0,k-5))*.55;nodes=[];
 U.forEach((p,i)=>nodes.push({{kind:'u',i,x:sx(p.px),y:sy(p.py),r:covers?rc*.85:2}}));R.forEach((p,i)=>nodes.push({{kind:'r',i,x:sx(p.px),y:sy(p.py),r:covers?rc:2.8}}));
 const vis=nodes.filter(n=>n.x>-30&&n.y>-30&&n.x<W+30&&n.y<H+30);
 if(covers&&vis.length<400)for(let pass=0;pass<4;pass++)for(let a=0;a<vis.length;a++)for(let b=a+1;b<vis.length;b++){{const p=vis[a],q=vis[b];
  let dx=q.x-p.x,dy=q.y-p.y;const d=Math.hypot(dx,dy)||.01,m=p.r+q.r+2;if(d>=m)continue;const f=(m-d)/d/2;dx*=f;dy*=f;p.x-=dx;p.y-=dy;q.x+=dx;q.y+=dy}}
 vis.forEach(n=>{{const p=n.kind==='u'?U[n.i]:R[n.i],ring=n.kind==='u'?'#ffffff':MC;
  if(!covers){{ctx.shadowColor=ring;ctx.shadowBlur=n.kind==='u'?6:10;ctx.fillStyle=ring;ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fill();ctx.shadowBlur=0;return}}
  const im=img(p.img),playing=n.kind==='r'&&state.id===p.track_id;
  if(playing||hover===n){{ctx.beginPath();ctx.arc(n.x,n.y,n.r+6+(playing?2*Math.sin(t/180):0),0,6.283);ctx.fillStyle=n.kind==='u'?'rgba(255,255,255,.25)':MC+'55';ctx.fill()}}
  ctx.save();ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.closePath();if(im&&im.complete&&im.naturalWidth){{ctx.clip();ctx.drawImage(im,n.x-n.r,n.y-n.r,2*n.r,2*n.r)}}else{{ctx.fillStyle='#2b2950';ctx.fill()}}ctx.restore();
  ctx.beginPath();ctx.arc(n.x,n.y,n.r+1.2,0,6.283);ctx.strokeStyle=ring;ctx.lineWidth=n.kind==='u'?1.6:2.4;ctx.stroke();
  if(n.kind==='r'&&(playing||hover===n)){{ctx.fillStyle='rgba(0,0,0,.45)';ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fill();ctx.fillStyle='#fff';
   if(playing&&state.s!=='loading'){{ctx.fillRect(n.x-4,n.y-5,3,10);ctx.fillRect(n.x+1,n.y-5,3,10)}}else{{ctx.beginPath();ctx.moveTo(n.x-3,n.y-6);ctx.lineTo(n.x+6,n.y);ctx.lineTo(n.x-3,n.y+6);ctx.fill()}}}}
  if(k>=12){{ctx.font='10px Geist Mono, monospace';ctx.textAlign='center';ctx.fillStyle='rgba(255,255,255,.75)';ctx.fillText(p.title.length>18?p.title.slice(0,17)+'…':p.title,n.x,n.y+n.r+10)}}}});
 nodes=vis}}
function frame(t){{if(fly){{const e=Math.min(1,(t-fly.t0)/750),q=1-Math.pow(1-e,3);view.k=fly.k0+(fly.k1-fly.k0)*q;view.x=fly.x0+(fly.x1-fly.x0)*q;view.y=fly.y0+(fly.y1-fly.y0)*q;dirty=true;if(e>=1)fly=null}}
 const key=view.k+','+view.x+','+view.y;if(dirty||key!==frame.last||state.id){{draw(t);dirty=false;frame.last=key}}requestAnimationFrame(frame)}}
function flyTo(x01,y01,k){{const k1=Math.min(window.KMAX,Math.max(1,k)),mx=W*window.EDGE,my=H*window.EDGE;
 const x1=Math.min(mx,Math.max(W-W*k1-mx,W/2-x01*W*k1)),y1=Math.min(my,Math.max(H-H*k1-my,H/2-y01*H*k1));fly={{t0:performance.now(),k0:view.k,x0:view.x,y0:view.y,k1,x1,y1}}}}
function fitMine(){{let pts=R.map(r=>[r.x,r.y]);if(!pts.length)pts=U.map(u=>[u.x,u.y]);if(!pts.length)return;
 const q=(arr,f)=>{{const s=arr.slice().sort((a,b)=>a-b);return s[Math.min(s.length-1,Math.max(0,Math.round(f*(s.length-1))))]}};
 const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x0=q(xs,.1),x1=q(xs,.9),y0=q(ys,.1),y1=q(ys,.9);
 flyTo((x0+x1)/2,(y0+y1)/2,Math.max(1.6,Math.min(1/Math.max(.03,(x1-x0)*1.5),1/Math.max(.03,(y1-y0)*1.5),18)))}}
{ZOOM_JS}
document.getElementById('zfit').onclick=fitMine;
{PLAYER_JS}
function setPlaying(id,s){{state={{id,s}};dirty=true}}
function noPreview(id){{tip.innerHTML='<div><b>'+esc(L.no_preview)+'</b></div>';tip.classList.add('on')}}
function pick(mx,my){{let best=null,bd=1e9;nodes.forEach(n=>{{const d=(n.x-mx)**2+(n.y-my)**2,r=Math.max(n.r,5)+3;if(d<r*r&&d<bd){{bd=d;best=n}}}});return best}}
function labelAt(mx,my){{for(let j=labelsDrawn.length-1;j>=0;j--){{const[info,x0,y0,w,h]=labelsDrawn[j];if(mx>=x0&&mx<=x0+w&&my>=y0&&my<=y0+h)return info}}return null}}
cv.addEventListener('mousemove',e=>{{dirty=true;if(drag){{tip.classList.remove('on');return}}const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;hover=pick(mx,my);let html='';
 if(hover){{const p=hover.kind==='u'?U[hover.i]:R[hover.i];html=(p.img?'<img src="'+esc(p.img)+'">':'')+'<div><b>'+esc(p.title)+'</b><small>'+esc(p.artist)+'</small>'+
  (hover.kind==='u'?'<small>'+esc(L.yours)+'</small>':'<em style="color:'+MC+'">'+esc(p.subgenre||'')+'</em><small>'+esc(L.because+' '+p.reason)+'</small><small>'+esc(state.id===p.track_id?L.pause:L.play)+'</small>')+'</div>'}}
 else{{const info=labelAt(mx,my);if(info){{if(info[0]==='g'){{const i=info[1];html='<div><b>'+esc(cap(GM.n[i]))+'</b><small>'+esc(L.in+' '+L2.names[L2.of[i]]+' · '+L1.names[L1.of[i]])+'</small></div>'}}
  else{{const lv=info[0]==='l1'?L1:L2,j=info[1],count=lv.of.filter(o=>o===j).length;html='<div><b>'+esc(lv.names[j])+'</b><small>'+esc(L.count.replace('{{n}}',count))+'</small></div>'}}}}}}
 cv.style.cursor=hover&&hover.kind==='r'?'pointer':'grab';if(!html){{tip.classList.remove('on');return}}
 tip.innerHTML=html;tip.style.left=Math.min(mx+18,W-350)+'px';tip.style.top=Math.min(my+100,H+40)+'px';tip.classList.add('on')}});
cv.addEventListener('mouseleave',()=>{{hover=null;tip.classList.remove('on');dirty=true}});
cv.addEventListener('click',e=>{{if(moved)return;const b=cv.getBoundingClientRect(),n=pick(e.clientX-b.left,e.clientY-b.top);
 if(n&&n.kind==='r'){{toggle(R[n.i].track_id);return}}const info=labelAt(e.clientX-b.left,e.clientY-b.top);
 if(info&&info[0]!=='g'){{const lv=info[0]==='l1'?L1:L2;flyTo(lv.cx[info[1]],lv.cy[info[1]],info[0]==='l1'?3.4:7)}}}});
const counts={{}};R.forEach(r=>{{if(r.subgenre)counts[r.subgenre]=(counts[r.subgenre]||0)+1}});
document.getElementById('chips').innerHTML=Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([g,c])=>'<button data-g="'+esc(g)+'">'+esc(g)+'<b>'+c+'</b></button>').join('');
document.querySelectorAll('#chips button').forEach(bt=>bt.addEventListener('click',()=>{{const g=bt.dataset.g,i=idx[g];
 document.querySelectorAll('#chips button').forEach(x=>x.classList.toggle('on',x===bt));const own=R.filter(r=>r.subgenre===g);
 const p=own.length?[own[0].x,own[0].y]:(i!==undefined?[GM.x[i],GM.y[i]]:null);if(!p)return;if(i!==undefined)pulse=i;flyTo(p[0],p[1],Math.max(view.k,9))}}));
document.getElementById('find').addEventListener('change',e=>{{const i=idx[e.target.value.trim().toLowerCase()]??idx[e.target.value.trim()];if(i===undefined)return;pulse=i;flyTo(GM.x[i],GM.y[i],Math.max(view.k,12))}});
layout();addEventListener('resize',layout);requestAnimationFrame(frame);
</script></body></html>"""
    _frame(html, height)
