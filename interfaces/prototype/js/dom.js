/* SVG, tooltip, axis and legend helpers shared by every chart. */
'use strict';
/* ================= DOM helpers ================= */
const $=q=>document.querySelector(q),$$=q=>[...document.querySelectorAll(q)];
const NS='http://www.w3.org/2000/svg';
function S(tag,attrs,parent){const e=document.createElementNS(NS,tag);if(attrs)for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e;}
const tip=$('#tip');
function showTip(html,ev){tip.innerHTML=html;tip.hidden=false;const r=tip.getBoundingClientRect();let x=ev.clientX+14,y=ev.clientY+14;if(x+r.width>innerWidth-8)x=ev.clientX-r.width-14;if(y+r.height>innerHeight-8)y=ev.clientY-r.height-14;tip.style.left=Math.max(8,x)+'px';tip.style.top=Math.max(8,y)+'px';}
const hideTip=()=>{tip.hidden=true;};
function yAxis(g,ys,tk,x0,x1,fmt){tk.forEach(v=>{S('line',{x1:x0,x2:x1,y1:ys(v),y2:ys(v),class:'grid-l'},g);const t=S('text',{x:x0-8,y:ys(v)+4,'text-anchor':'end',class:'lbl'},g);t.textContent=fmt(v);});}
function legend(el,items){el.innerHTML=items.map(i=>`<span><i class="sw ${i.kind||''}" style="${i.kind==='dash'?'border-color:'+i.c:'background:'+i.c}"></i>${esc(i.t)}</span>`).join('');}
