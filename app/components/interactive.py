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

@lru_cache(maxsize=2)
def _tree_table(lang: str) -> str:
    """The atlas of genres (core/genretree.py) as compact JSON, names in the page's language."""
    from core import genretree

    t = genretree.tree()
    lang = lang if lang in ("fr", "en") else "fr"
    g = t["genres"]
    return js_data({"main": [{"n": m[lang], "h": m["hue"], "l": m["light"], "x": m["x"], "y": m["y"], "c": m["n"]}
                             for m in t["main"]],
                    "sub": [{"n": s[lang], "m": s["main"], "x": s["x"], "y": s["y"], "c": s["n"]} for s in t["sub"]],
                    "g": {"n": [r[0] for r in g], "s": [r[1] for r in g], "x": [r[2] for r in g], "y": [r[3] for r in g]},
                    "o": t["outline"]})


SOUND_MAP_CSS = """
html,body{margin:0;background:transparent;font-family:__FONT__;-webkit-font-smoothing:antialiased;overflow:hidden}
.space{position:relative;border-radius:22px;overflow:hidden;background:#070816}
.top{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;padding:12px 16px 6px;font-size:12px;color:rgba(255,255,255,.82)}
.top span{display:flex;align-items:center;gap:7px}
.top b.neb{width:34px;height:10px;border-radius:5px;background:linear-gradient(90deg,#2a0f5c,#812581,#e55964,#fec287,#fcfdbf)}
.top b.dots{width:30px;height:10px;background:radial-gradient(circle,#ff8fb1 2px,transparent 2.6px) 0 1px/10px 10px,
 radial-gradient(circle,#5fd4ff 2px,transparent 2.6px) 5px 0/10px 10px,radial-gradient(circle,#ffd36e 2px,transparent 2.6px) 2px 5px/10px 10px}
.top b.ring{width:14px;height:14px;border-radius:50%;border:2px solid __C__;box-shadow:0 0 8px __C__}
.top i.rec{width:9px;height:9px;border-radius:50%;display:inline-block;background:__C__;box-shadow:0 0 8px __C__}
.find{margin-left:auto;position:relative}
.find input{font:500 12px __FONT__;padding:7px 14px;border-radius:999px;border:1.5px solid rgba(255,255,255,.28);
 background:rgba(255,255,255,.08);color:#fff;outline:none;width:260px}
.find input::placeholder{color:rgba(255,255,255,.5)}
.sug{position:absolute;right:0;top:36px;width:320px;background:rgba(14,15,34,.96);border:1px solid rgba(255,255,255,.16);border-radius:14px;
 padding:6px;display:none;z-index:9;backdrop-filter:blur(8px)}
.sug.on{display:block}.sug div{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:9px;color:#fff;font-size:12px;cursor:pointer}
.sug div:hover,.sug div.sel{background:rgba(255,255,255,.1)}.sug small{margin-left:auto;color:rgba(255,255,255,.5)}
.sug i{width:8px;height:8px;border-radius:50%;flex:none}
.chips{display:flex;gap:6px;overflow-x:auto;padding:4px 16px 8px;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}
.chips button{flex:none;font:500 11.5px __FONT__;color:#fff;background:rgba(255,255,255,.07);border:1.5px solid rgba(255,255,255,.22);
 border-radius:999px;padding:5px 11px;cursor:pointer;white-space:nowrap}.chips button b{color:__C__;margin-left:6px;font-weight:600}
.chips button:hover,.chips button.on{background:rgba(255,255,255,.18);border-color:__C__}
.stage{position:relative}
canvas{display:block;width:100%;height:__H__px}
#ov{position:absolute;inset:0;pointer-events:none}
.tip{position:absolute;pointer-events:none;display:flex;gap:12px;align-items:center;background:rgba(14,15,34,.94);color:#fff;padding:10px 14px 10px 10px;
 border:1px solid rgba(255,255,255,.18);border-radius:14px;font-size:12px;line-height:1.45;opacity:0;transform:translateY(4px);
 transition:opacity .15s,transform .15s;max-width:360px;z-index:7;backdrop-filter:blur(8px)}
.tip.on{opacity:1;transform:none}.tip img{width:58px;height:58px;border-radius:50%;object-fit:cover;flex:none}
.tip img.sq{border-radius:10px}.tip b{display:block;font-size:13.5px}
.tip small{display:block;color:rgba(255,255,255,.66)}.tip em{display:block;font-style:normal;font-weight:600;margin-top:2px}
.tip .act{color:rgba(255,255,255,.9);margin-top:4px;font-weight:600}
""" + ZOOM_CSS

SOUND_MAP_JS = r"""
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),ov=document.getElementById('ov'),octx=ov.getContext('2d'),tip=document.getElementById('tip');
let W=0,H=0,dirty=true;
const NG=T.g.n.length,NM=T.main.length,NA=A.id.length,DPR=()=>devicePixelRatio||1;
const cap=s=>s?s.charAt(0).toUpperCase()+s.slice(1):s;
const hsl=(m,a=1,dl=0,sat=78)=>`hsla(${T.main[m].h},${sat}%,${Math.min(96,T.main[m].l+dl)}%,${a})`;
const MAINC=T.main.map((_,m)=>hsl(m));
const gidx={};T.g.n.forEach((n,i)=>gidx[n]=i);
const mainOfG=i=>T.sub[T.g.s[i]].m;
const pic=i=>{const p=A.p[i];return !p?'':(p.length===32?'https://cdn-images.dzcdn.net/images/artist/'+p+'/250x250-000000-80-0-0.jpg':p)};
const ramp=(k,a,b)=>Math.max(0,Math.min(1,(k-a)/(b-a)));
const hash=i=>{let h=(i+1)*2654435761>>>0;h^=h>>>15;h=Math.imul(h,2246822519)>>>0;h^=h>>>13;return (h>>>0)/4294967296};
// discoveries: scattered around their sub-genre, the same way every time
R.forEach((p,i)=>{const u=Math.max(1e-6,hash(977+i*2)),v=hash(978+i*2),r=.0034*Math.sqrt(-2*Math.log(u));p.px=p.x+Math.cos(6.283*v)*r/1.6;p.py=p.y+Math.sin(6.283*v)*r});
const nearestG=(x,y)=>{let b=0,bd=1e9;for(let i=0;i<NG;i++){const d=(T.g.x[i]-x)**2+(T.g.y[i]-y)**2;if(d<bd){bd=d;b=i}}return b};
const explored=new Set();R.forEach(r=>{const g=gidx[r.subgenre];if(g!==undefined)explored.add(g)});
// where to zoom: the discoveries grouped by sub-genre district
const groups={};R.forEach((r,i)=>{const g=gidx[r.subgenre]!==undefined?gidx[r.subgenre]:nearestG(r.x,r.y);const s=T.g.s[g];(groups[s]=groups[s]||[]).push(i)});
const zones=Object.entries(groups).map(([s,ids])=>{const xs=ids.map(i=>R[i].px),ys=ids.map(i=>R[i].py);
 return{s:+s,ids,x:xs.reduce((a,b)=>a+b)/xs.length,y:ys.reduce((a,b)=>a+b)/ys.length,x0:Math.min(...xs),x1:Math.max(...xs),y0:Math.min(...ys),y1:Math.max(...ys)}});
const pathIdx=P.map(([a,b])=>[gidx[a],gidx[b]]).filter(([a,b])=>a!==undefined&&b!==undefined);
const imgs={};function img(u){if(!u)return null;if(!imgs[u]){const im=new Image();im.onload=()=>dirty=true;im.src=u;imgs[u]=im}return imgs[u]}
// the nebula: the density of your artists (weighted by listening and library), in magma colours
const STOPS=[[0,[7,8,22]],[.12,[28,16,68]],[.25,[79,18,123]],[.4,[129,37,129]],[.55,[181,54,122]],[.68,[229,89,100]],[.8,[251,135,97]],[.9,[254,194,135]],[1,[252,253,191]]];
const LUT=new Uint8ClampedArray(256*4);for(let i=0;i<256;i++){const t=i/255;let a=STOPS[0],b=STOPS[STOPS.length-1];
 for(let j=0;j<STOPS.length-1;j++)if(t>=STOPS[j][0]&&t<=STOPS[j+1][0]){a=STOPS[j];b=STOPS[j+1];break}
 const f=(t-a[0])/Math.max(1e-6,b[0]-a[0]);for(let c=0;c<3;c++)LUT[i*4+c]=a[1][c]+(b[1][c]-a[1][c])*f;LUT[i*4+3]=Math.min(225,Math.pow(t,.8)*300)}
const dc=document.createElement('canvas'),cc=document.createElement('canvas'),cctx=cc.getContext('2d');let G=null;
let geo=null;
function buildGeo(){const outline=new Path2D();T.o.forEach(([x,y],i)=>i?outline.lineTo(x*W,y*H):outline.moveTo(x*W,y*H));outline.closePath();
 geo={outline,tint:[],b1:new Path2D(),b2:new Path2D(),b3:new Path2D(),ok:false};
 if(!window.d3||!d3.Delaunay)return;
 const pts=new Float64Array(NG*2);for(let i=0;i<NG;i++){pts[2*i]=T.g.x[i]*W;pts[2*i+1]=T.g.y[i]*H}
 const del=new d3.Delaunay(pts),vor=del.voronoi([-W*.05,-H*.05,W*1.05,H*1.05]);
 for(let m=0;m<NM;m++)geo.tint.push(new Path2D());
 for(let i=0;i<NG;i++)vor.renderCell(i,geo.tint[mainOfG(i)]);
 const he=del.halfedges,tr=del.triangles,ccs=vor.circumcenters;
 for(let e=0;e<he.length;e++){const j=he[e];if(j<e)continue;const a=tr[e],b=tr[e%3===2?e-2:e+1],t1=Math.floor(e/3),t2=Math.floor(j/3);
  const sa=T.g.s[a],sb=T.g.s[b],p=T.sub[sa].m!==T.sub[sb].m?geo.b1:(sa!==sb?geo.b2:geo.b3);p.moveTo(ccs[2*t1],ccs[2*t1+1]);p.lineTo(ccs[2*t2],ccs[2*t2+1])}
 geo.ok=true}
function layout(){const d=DPR();W=cv.clientWidth;H=cv.clientHeight;cv.width=ov.width=W*d;cv.height=ov.height=H*d;
 dc.width=cc.width=Math.ceil(W/4);dc.height=cc.height=Math.ceil(H/4);buildGeo();dirty=true}
const sx=x=>x*W*view.k+view.x,sy=y=>y*H*view.k+view.y;
const world=c=>{const d=DPR();c.setTransform(d*view.k,0,0,d*view.k,d*view.x,d*view.y)},screen=c=>{const d=DPR();c.setTransform(d,0,0,d,0,0)};
function nebula(){const k=view.k,q=1/4,w=cc.width,h=cc.height;if(!G||G.length!==w*h)G=new Float32Array(w*h);else G.fill(0);
 const R0=Math.max(1.3,9*Math.pow(k,.5)*q),s2=2*(R0*.55)**2,rad=Math.ceil(R0*1.5),K=[];
 for(let dy=-rad;dy<=rad;dy++)for(let dx=-rad;dx<=rad;dx++){const v=Math.exp(-(dx*dx+dy*dy)/s2);if(v>.03)K.push(dx+dy*w,dx,dy,v)}
 for(let i=0;i<NA;i++){const cx=Math.round(sx(A.x[i])*q),cy=Math.round(sy(A.y[i])*q);if(cx<-rad||cy<-rad||cx>=w+rad||cy>=h+rad)continue;
  const base=cy*w+cx,wt=A.w[i];for(let j=0;j<K.length;j+=4){const X=cx+K[j+1],Y=cy+K[j+2];if(X<0||Y<0||X>=w||Y>=h)continue;G[base+K[j]]+=K[j+3]*wt}}
 const sample=[];for(let p=0;p<G.length;p+=3)if(G[p]>0)sample.push(G[p]);sample.sort((a,b)=>a-b);
 const top=sample.length?sample[Math.floor(sample.length*.993)]:1;
 const out=cctx.createImageData(w,h),o=out.data;for(let p=0,j=0;p<G.length;p++,j+=4){const v=G[p];if(v<=0)continue;
  const t=Math.min(255,Math.round(Math.pow(v/top,.9)*255))*4;o[j]=LUT[t];o[j+1]=LUT[t+1];o[j+2]=LUT[t+2];o[j+3]=LUT[t+3]}
 cctx.putImageData(out,0,0);ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.globalAlpha=.92-.42*ramp(k,4,12);ctx.drawImage(cc,0,0,W,H);ctx.globalAlpha=1}
let nodes=[],labelsDrawn=[],hover=null,fly=null,pulse=null,state={},zoneHits=[];
function draw(){const k=view.k;screen(ctx);ctx.fillStyle='#070816';ctx.fillRect(0,0,W,H);
 world(ctx);ctx.save();ctx.clip(geo.outline);ctx.fillStyle='#0c0e27';ctx.fill(geo.outline);
 if(geo.ok)geo.tint.forEach((p,m)=>{ctx.fillStyle=hsl(m,.15,-12);ctx.fill(p)});
 screen(ctx);nebula();world(ctx);
 if(geo.ok){ctx.lineJoin='round';
  if(k>=4){ctx.strokeStyle=`rgba(214,224,255,${.09*ramp(k,4,8)})`;ctx.lineWidth=.8/k;ctx.stroke(geo.b3)}
  ctx.strokeStyle=`rgba(214,224,255,${.3*ramp(k,1.25,1.9)})`;ctx.lineWidth=1/k;ctx.stroke(geo.b2);
  ctx.strokeStyle='rgba(230,236,255,.55)';ctx.lineWidth=1.5/k;ctx.stroke(geo.b1)}
 ctx.restore();world(ctx);ctx.strokeStyle='rgba(170,182,255,.45)';ctx.lineWidth=1.4/k;ctx.stroke(geo.outline);screen(ctx);
 // paths from your sub-genres to the ones explored (sub-genres mode)
 pathIdx.forEach(([a,b])=>{const x1=sx(T.g.x[a]),y1=sy(T.g.y[a]),x2=sx(T.g.x[b]),y2=sy(T.g.y[b]),mx=(x1+x2)/2+(y2-y1)*.2,my=(y1+y2)/2-(x2-x1)*.2;
  ctx.strokeStyle=MC;ctx.globalAlpha=.5;ctx.lineWidth=1.2;ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(x1,y1);ctx.quadraticCurveTo(mx,my,x2,y2);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1});
 // your artists: one point each, in the colour of its main genre; photos once close enough
 const photos=k>=7,vis=[];
 for(let i=0;i<NA;i++){const x=sx(A.x[i]),y=sy(A.y[i]);if(x<-30||y<-30||x>W+30||y>H+30)continue;vis.push(i)}
 nodes=[];
 if(!photos){const grow=Math.min(2.6,.85+k*.2),byM=Array.from({length:NM},()=>new Path2D()),rings=new Path2D();
  vis.forEach(i=>{const x=sx(A.x[i]),y=sy(A.y[i]),r=(.75+.3*Math.sqrt(A.w[i]))*grow;byM[A.m[i]].moveTo(x+r,y);byM[A.m[i]].arc(x,y,r,0,6.283);
   if(A.pl[i]>0){rings.moveTo(x+r+1.6,y);rings.arc(x,y,r+1.6,0,6.283)}nodes.push({kind:'a',i,x,y,r})});
  byM.forEach((p,m)=>{ctx.fillStyle=hsl(m,.92,8,88);ctx.fill(p)});ctx.strokeStyle='rgba(255,255,255,.85)';ctx.lineWidth=1;ctx.stroke(rings)}
 else{const grow=Math.min(1.7,1+(k-7)*.06);vis.forEach(i=>{nodes.push({kind:'a',i,x:sx(A.x[i]),y:sy(A.y[i]),r:Math.min(24,(6.5+2.3*Math.sqrt(A.w[i]))*grow)})})}
 // the discoveries
 const covers=k>=5,rc=7+Math.min(10,Math.max(0,k-5))*.55;
 R.forEach((p,i)=>{const x=sx(p.px),y=sy(p.py);if(x<-30||y<-30||x>W+30||y>H+30)return;nodes.push({kind:'r',i,x,y,r:covers?rc:3.2})});
 if(photos||covers){const big=nodes.filter(n=>n.kind==='r'||photos);if(big.length<420)for(let pass=0;pass<4;pass++)for(let a=0;a<big.length;a++)for(let b=a+1;b<big.length;b++){
  const p=big[a],q=big[b];let dx=q.x-p.x,dy=q.y-p.y;const d=Math.hypot(dx,dy)||.01,m=p.r+q.r+2;if(d>=m)continue;const f=(m-d)/d/2;dx*=f;dy*=f;p.x-=dx;p.y-=dy;q.x+=dx;q.y+=dy}}
 if(photos)nodes.filter(n=>n.kind==='a').forEach(n=>{const i=n.i,im=img(pic(i));ctx.save();ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);
  if(im&&im.complete&&im.naturalWidth){ctx.clip();ctx.drawImage(im,n.x-n.r,n.y-n.r,2*n.r,2*n.r)}else{ctx.fillStyle=hsl(A.m[i],1,-18);ctx.fill();
   ctx.fillStyle='#fff';ctx.font=`600 ${Math.round(n.r)}px Geist Mono, monospace`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText((A.n[i]||'?').charAt(0),n.x,n.y+1)}
  ctx.restore();ctx.beginPath();ctx.arc(n.x,n.y,n.r+1.4,0,6.283);ctx.strokeStyle=A.pl[i]>0?'#fff':hsl(A.m[i],1,10,90);ctx.lineWidth=A.pl[i]>0?2.2:1.6;ctx.stroke();
  if(k>=11){ctx.font='10px Geist Mono, monospace';ctx.textAlign='center';ctx.textBaseline='alphabetic';ctx.fillStyle='rgba(255,255,255,.82)';
   const nm=A.n[i]||'';ctx.fillText(nm.length>18?nm.slice(0,17)+'…':nm,n.x,n.y+n.r+11)}});
 nodes.filter(n=>n.kind==='r').forEach(n=>{const p=R[n.i];
  if(!covers){ctx.shadowColor=MC;ctx.shadowBlur=10;ctx.fillStyle=MC;ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);ctx.fill();ctx.shadowBlur=0;
   ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.stroke();return}
  const im=img(p.img);ctx.save();ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,6.283);if(im&&im.complete&&im.naturalWidth){ctx.clip();ctx.drawImage(im,n.x-n.r,n.y-n.r,2*n.r,2*n.r)}
  else{ctx.fillStyle='#2b2950';ctx.fill()}ctx.restore();ctx.beginPath();ctx.arc(n.x,n.y,n.r+1.4,0,6.283);ctx.strokeStyle=MC;ctx.lineWidth=2.6;ctx.stroke();
  if(k>=12){ctx.font='10px Geist Mono, monospace';ctx.textAlign='center';ctx.textBaseline='alphabetic';ctx.fillStyle='rgba(255,255,255,.82)';ctx.fillText(p.title.length>18?p.title.slice(0,17)+'…':p.title,n.x,n.y+n.r+11)}});
 // names: main genres, then sub-genres, then every genre, never overlapping
 const cell=10,grid=new Set();labelsDrawn=[];
 const put=(text,x,y,fs,weight,fill,alpha,force,info)=>{if(alpha<=.03||x<-90||y<-20||x>W+90||y>H+20)return;const w=text.length*fs*.6,x0=x-w/2,y0=y-fs/2,cs=[];
  for(let cx=Math.floor(x0/cell);cx<=Math.floor((x0+w)/cell);cx++)for(let cy=Math.floor(y0/cell);cy<=Math.floor((y0+fs)/cell);cy++)cs.push(cx+','+cy);
  if(!force&&cs.some(c=>grid.has(c)))return;cs.forEach(c=>grid.add(c));ctx.globalAlpha=alpha;ctx.font=`${weight} ${fs}px Geist Mono, monospace`;
  ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineJoin='round';ctx.strokeStyle='rgba(7,8,22,.88)';ctx.lineWidth=Math.max(3,fs*.3);ctx.strokeText(text,x,y);
  ctx.fillStyle=fill;ctx.fillText(text,x,y);ctx.globalAlpha=1;labelsDrawn.push([info,x0,y0,w,fs])};
 const a1=1-ramp(k,2.3,3.4),a2=ramp(k,1.3,1.9)*(1-ramp(k,16,30)),a3=ramp(k,3.3,4.8);
 if(pulse!==null){if(pulse.g!==undefined)put(cap(T.g.n[pulse.g]),sx(T.g.x[pulse.g]),sy(T.g.y[pulse.g])-12,14,700,'#fff',1,true,['g',pulse.g])}
 T.main.forEach((m,j)=>put(m.n,sx(m.x),sy(m.y),24,700,'#ffffff',a1,false,['m',j]));
 T.sub.forEach((s,j)=>put(s.n,sx(s.x),sy(s.y),13.5,600,hsl(s.m,1,22,90),a2,false,['s',j]));
 explored.forEach(i=>put(T.g.n[i],sx(T.g.x[i]),sy(T.g.y[i])-10,12,650,MC,Math.max(a3,.9*ramp(k,1.6,2.6)),false,['g',i]));
 if(a3>0){const lim=Math.min(NG,Math.round(30*Math.pow(k,1.8)));for(let i=0;i<lim;i++)put(T.g.n[i],sx(T.g.x[i]),sy(T.g.y[i]),11,450,'rgba(236,238,255,.9)',a3*.92,false,['g',i])}
}
// the overlay: where to zoom for the discoveries (rings that breathe), the hovered and the playing points
function overlay(t){const k=view.k;screen(octx);octx.clearRect(0,0,W,H);zoneHits=[];
 const za=1-ramp(k,4.5,7);if(za>0)zones.forEach(z=>{const x=sx(z.x),y=sy(z.y),spread=Math.max((z.x1-z.x0)*W,(z.y1-z.y0)*H)*k/2,r=Math.max(14,spread+10)+3*Math.sin(t/420+z.s);
  if(x<-r||y<-r||x>W+r||y>H+r)return;const g=octx.createRadialGradient(x,y,r*.2,x,y,r*1.5);g.addColorStop(0,MC+'00');g.addColorStop(.62,MC+'40');g.addColorStop(1,MC+'00');
  octx.globalAlpha=za;octx.fillStyle=g;octx.beginPath();octx.arc(x,y,r*1.5,0,6.283);octx.fill();
  octx.strokeStyle=MC;octx.lineWidth=2;octx.setLineDash([6,5]);octx.lineDashOffset=-t/60;octx.beginPath();octx.arc(x,y,r,0,6.283);octx.stroke();octx.setLineDash([]);
  const txt=String(z.ids.length),bw=12+txt.length*7.5;octx.fillStyle=MC;octx.beginPath();octx.roundRect(x+r*.7-bw/2,y-r*.7-10,bw,20,10);octx.fill();
  octx.fillStyle='#071023';octx.font='700 12px Geist Mono, monospace';octx.textAlign='center';octx.textBaseline='middle';octx.fillText(txt,x+r*.7,y-r*.7);octx.globalAlpha=1;
  zoneHits.push({z,x,y,r})});
 const ring=(n,c,w,extra)=>{octx.beginPath();octx.arc(n.x,n.y,n.r+4+extra,0,6.283);octx.strokeStyle=c;octx.lineWidth=w;octx.stroke()};
 if(hover&&hover.kind)ring(hover,'#fff',2,0);
 nodes.forEach(n=>{if(n.kind==='r'&&state.id===R[n.i].track_id){ring(n,MC,2.5,2+2*Math.sin(t/180));
  if(n.r>6){octx.fillStyle='rgba(0,0,0,.45)';octx.beginPath();octx.arc(n.x,n.y,n.r,0,6.283);octx.fill();octx.fillStyle='#fff';
   if(state.s!=='loading'){octx.fillRect(n.x-4,n.y-5,3,10);octx.fillRect(n.x+1,n.y-5,3,10)}else{octx.beginPath();octx.arc(n.x,n.y,2,0,6.283);octx.fill()}}}});
 if(pulse&&pulse.a!==undefined){const i=pulse.a,x=sx(A.x[i]),y=sy(A.y[i]),r=10+6*((t/700)%1)*3;octx.strokeStyle=`rgba(255,255,255,${1-((t/700)%1)})`;octx.lineWidth=2;octx.beginPath();octx.arc(x,y,r,0,6.283);octx.stroke()}}
function frame(t){if(fly){const e=Math.min(1,(t-fly.t0)/750),q=1-Math.pow(1-e,3);view.k=fly.k0+(fly.k1-fly.k0)*q;view.x=fly.x0+(fly.x1-fly.x0)*q;view.y=fly.y0+(fly.y1-fly.y0)*q;dirty=true;if(e>=1)fly=null}
 const key=view.k+','+view.x+','+view.y;if(dirty||key!==frame.last){draw();dirty=false;frame.last=key}overlay(t);requestAnimationFrame(frame)}
function flyTo(x01,y01,k){const k1=Math.min(window.KMAX,Math.max(1,k)),mx=W*window.EDGE,my=H*window.EDGE;
 const x1=Math.min(mx,Math.max(W-W*k1-mx,W/2-x01*W*k1)),y1=Math.min(my,Math.max(H-H*k1-my,H/2-y01*H*k1));fly={t0:performance.now(),k0:view.k,x0:view.x,y0:view.y,k1,x1,y1}}
const fitBox=(x0,x1,y0,y1,kmin,kmax)=>flyTo((x0+x1)/2,(y0+y1)/2,Math.max(kmin,Math.min(kmax,1/Math.max(.02,(x1-x0)*1.6),1/Math.max(.02,(y1-y0)*1.6))));
function fitMine(){if(!R.length){resetView();return}const q=(arr,f)=>{const s=arr.slice().sort((a,b)=>a-b);return s[Math.min(s.length-1,Math.max(0,Math.round(f*(s.length-1))))]};
 const xs=R.map(p=>p.px),ys=R.map(p=>p.py);fitBox(q(xs,.1),q(xs,.9),q(ys,.1),q(ys,.9),1.4,10)}
__ZOOM_JS__
document.getElementById('zfit').onclick=fitMine;
__PLAYER_JS__
function setPlaying(id,s){state={id,s}}
function noPreview(id){tip.innerHTML='<div><b>'+esc(L.no_preview)+'</b></div>';tip.classList.add('on')}
function pick(mx,my){let best=null,bd=1e9;for(const n of nodes){const d=(n.x-mx)**2+(n.y-my)**2,r=Math.max(n.r,4)+2;if(d<r*r&&(d<bd||(best&&best.kind==='a'&&n.kind==='r'))){bd=d;best=n}}return best}
function zoneAt(mx,my){for(const h of zoneHits){if((h.x-mx)**2+(h.y-my)**2<h.r*h.r)return h.z}return null}
function labelAt(mx,my){for(let j=labelsDrawn.length-1;j>=0;j--){const[info,x0,y0,w,h]=labelsDrawn[j];if(mx>=x0&&mx<=x0+w&&my>=y0&&my<=y0+h)return info}return null}
const fmt=(s,n)=>s.replace('{n}',n);
function artistTip(i){const s=T.sub[A.s[i]],m=T.main[A.m[i]],lines=[];
 if(A.pl[i])lines.push(fmt(L.plays,A.pl[i])+(A.mn[i]?' · '+fmt(L.minutes,A.mn[i]):''));
 if(A.lt[i])lines.push(fmt(L.lists,A.lt[i]));if(A.fa[i])lines.push(fmt(L.favs,A.fa[i]));
 return (pic(i)?'<img src="'+esc(pic(i))+'">':'')+'<div><b>'+esc(A.n[i])+'</b><em style="color:'+hsl(A.m[i],1,14,90)+'">'+esc(m.n+(A.lv[i]<=1?' › '+s.n:'')+(A.lv[i]===0&&A.g[i]?' › '+cap(A.g[i]):''))+'</em>'+
  lines.map(l=>'<small>'+esc(l)+'</small>').join('')+'<small>'+esc(L['lv'+A.lv[i]])+'</small><div class="act">'+esc(L.open)+'</div></div>'}
cv.addEventListener('mousemove',e=>{if(drag){tip.classList.remove('on');hover=null;return}const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top;hover=pick(mx,my);let html='';
 if(hover&&hover.kind==='r'){const p=R[hover.i];html=(p.img?'<img class="sq" src="'+esc(p.img)+'">':'')+'<div><b>'+esc(p.title)+'</b><small>'+esc(p.artist)+'</small><em style="color:'+MC+'">'+esc(p.subgenre||'')+'</em><small>'+esc(L.because+' '+p.reason)+'</small><div class="act">'+esc(state.id===p.track_id?L.pause:L.play)+'</div></div>'}
 else if(hover&&hover.kind==='a')html=artistTip(hover.i);
 else{const z=zoneAt(mx,my);if(z){html='<div><b style="color:'+MC+'">'+esc(fmt(L.zone,z.ids.length))+'</b><small>'+esc(T.sub[z.s].n+' · '+T.main[T.sub[z.s].m].n)+'</small><div class="act">'+esc(L.zoom_in)+'</div></div>';hover={zone:z}}
  else{const info=labelAt(mx,my);if(info){if(info[0]==='g'){const i=info[1];html='<div><b>'+esc(cap(T.g.n[i]))+'</b><small>'+esc(T.sub[T.g.s[i]].n+' · '+T.main[mainOfG(i)].n)+'</small></div>'}
   else{const lv=info[0]==='m'?T.main:T.sub,j=info[1];html='<div><b>'+esc(lv[j].n)+'</b><small>'+esc(fmt(L.count,lv[j].c))+'</small><div class="act">'+esc(L.zoom_in)+'</div></div>'}}}}
 cv.style.cursor=hover?'pointer':'grab';if(!html){tip.classList.remove('on');return}
 tip.innerHTML=html;tip.style.left=Math.min(mx+18,W-370)+'px';tip.style.top=Math.min(my+96,H+30)+'px';tip.classList.add('on')});
cv.addEventListener('mouseleave',()=>{hover=null;tip.classList.remove('on')});
cv.addEventListener('click',e=>{if(moved)return;const b=cv.getBoundingClientRect(),mx=e.clientX-b.left,my=e.clientY-b.top,n=pick(mx,my);
 if(n&&n.kind==='r'){toggle(R[n.i].track_id);return}
 if(n&&n.kind==='a'){window.open('https://www.deezer.com/artist/'+A.id[n.i],'_blank','noopener');return}
 const z=zoneAt(mx,my);if(z){fitBox(z.x0,z.x1,z.y0,z.y1,6,16);return}
 const info=labelAt(mx,my);if(info&&info[0]!=='g'){const lv=info[0]==='m'?T.main:T.sub;flyTo(lv[info[1]].x,lv[info[1]].y,info[0]==='m'?2.6:6)}});
// chips: each explored sub-genre
const counts={};R.forEach(r=>{if(r.subgenre)counts[r.subgenre]=(counts[r.subgenre]||0)+1});
document.getElementById('chips').innerHTML=Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([g,c])=>'<button data-g="'+esc(g)+'">'+esc(g)+'<b>'+c+'</b></button>').join('');
document.querySelectorAll('#chips button').forEach(bt=>bt.addEventListener('click',()=>{const g=bt.dataset.g,i=gidx[g];
 document.querySelectorAll('#chips button').forEach(x=>x.classList.toggle('on',x===bt));const own=R.filter(r=>r.subgenre===g);
 if(own.length){const xs=own.map(p=>p.px),ys=own.map(p=>p.py);pulse=i!==undefined?{g:i}:null;fitBox(Math.min(...xs),Math.max(...xs),Math.min(...ys),Math.max(...ys),8,16)}}));
// search a genre or an artist
const norm=s=>s.normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase();
const index=T.g.n.map((n,i)=>[norm(n),'g',i]).concat(A.n.map((n,i)=>[norm(n||''),'a',i]));
const find=document.getElementById('find'),sug=document.getElementById('sug');let found=[],sel=0;
function go(f){if(!f)return;sug.classList.remove('on');if(f[1]==='g'){const i=f[2];pulse={g:i};find.value=cap(T.g.n[i]);flyTo(T.g.x[i],T.g.y[i],Math.max(view.k,12))}
 else{const i=f[2];pulse={a:i};find.value=A.n[i];flyTo(A.x[i],A.y[i],Math.max(view.k,14))}}
function showSug(){sug.innerHTML=found.map((f,j)=>'<div data-j="'+j+'" class="'+(j===sel?'sel':'')+'"><i style="background:'+(f[1]==='g'?hsl(mainOfG(f[2])):hsl(A.m[f[2]]))+'"></i>'+
  esc(f[1]==='g'?cap(T.g.n[f[2]]):A.n[f[2]])+'<small>'+esc(f[1]==='g'?L.genre:L.artist)+'</small></div>').join('');sug.classList.toggle('on',found.length>0);
 sug.querySelectorAll('div').forEach(d=>d.addEventListener('mousedown',e=>{e.preventDefault();go(found[+d.dataset.j])}))}
find.addEventListener('input',()=>{const q=norm(find.value.trim());sel=0;if(q.length<2){found=[];showSug();return}
 const starts=[],has=[];for(const f of index){if(f[0].startsWith(q))starts.push(f);else if(f[0].includes(q))has.push(f);if(starts.length>=8)break}found=starts.concat(has).slice(0,8);showSug()});
find.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){sel=Math.min(found.length-1,sel+1);showSug();e.preventDefault()}else if(e.key==='ArrowUp'){sel=Math.max(0,sel-1);showSug();e.preventDefault()}
 else if(e.key==='Enter')go(found[sel]);else if(e.key==='Escape')sug.classList.remove('on')});
find.addEventListener('blur',()=>setTimeout(()=>sug.classList.remove('on'),120));
layout();addEventListener('resize',layout);requestAnimationFrame(frame);
"""


def sound_map(artists: dict, recs: list[dict], paths: list[tuple[str, str]], labels: dict, color: str, lang: str,
              height: int = 800) -> None:
    """The map of sound: an atlas of every genre (main genres, sub-genres, then the 6,291 genres
    of Every Noise at Once) where each point is an artist of your music, coloured by its main
    genre, the nebula is where your music lives, and rings show where to zoom for the discoveries.
    Hover a point for its name, click it to open the artist on Deezer; click a discovery to hear
    it. artists: columns from core.atlas.columns(); recs: {title, artist, img, track_id, reason,
    subgenre, x, y}; paths: (from genre, to genre) for the sub-genres mode."""
    legend = (f"<span><b class='neb'></b>{escape(labels['density'])}</span>"
              f"<span><b class='dots'></b>{escape(labels['artists'])}</span>"
              f"<span><i class='rec'></i>{escape(labels['found'])}</span>"
              f"<span><b class='ring'></b>{escape(labels['zones'])}</span>")
    keys = ("play", "pause", "no_preview", "because", "count", "plays", "minutes", "lists", "favs", "open", "lv0", "lv1", "lv2",
            "zone", "zoom_in", "genre", "artist")
    css = SOUND_MAP_CSS.replace("__FONT__", FONT).replace("__C__", color).replace("__H__", str(height - 92))
    script = (f"window.KMAX=80;window.EDGE=.06;const T={_tree_table(lang)},A={js_data(artists)},R={js_data(recs)},"
              f"P={js_data(paths)},MC={js_data(color)},L={js_data({k: labels[k] for k in keys})};{ESC_JS}"
              + SOUND_MAP_JS.replace("__ZOOM_JS__", ZOOM_JS).replace("__PLAYER_JS__", PLAYER_JS))
    html = (f'<!doctype html><html><head><meta charset="utf-8">{FONT_LINK}<style>{css}</style>'
            '<script src="https://cdn.jsdelivr.net/npm/d3-delaunay@6/dist/d3-delaunay.min.js"></script></head><body>'
            f'<div class="space"><div class="top">{legend}<div class="find"><input id="find" autocomplete="off" '
            f'placeholder="{escape(labels["search"])}"><div class="sug" id="sug"></div></div></div>'
            '<div class="chips" id="chips"></div><div class="stage"><canvas id="c"></canvas><canvas id="ov"></canvas></div>'
            '<div class="tip" id="tip"></div>'
            f'<div class="zoom"><button id="zfit" title="{escape(labels["fit"])}">◎</button><button id="zin">+</button>'
            f'<button id="zout">−</button><button id="zreset" title="{escape(labels["whole"])}">⟲</button></div>'
            f'<div class="hint">{escape(labels["hint"])}</div></div><script>{script}</script></body></html>')
    _frame(html, height)
