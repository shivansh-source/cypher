/* Investment view: budget slider, frontier chart and candidate-control table. */
'use strict';
/* ================= Investment view ================= */
function renderInvest(){
  const budget=+$('#budget').value;$('#budgetV').textContent=inr(budget);
  if(!OPT.ready){$('#invStats').innerHTML='<div class="loading" style="grid-column:1/-1;padding-top:12px">Jointly re-simulating all 1,024 portfolios…</div>';return;}
  const opt=bestFor(budget);const m=custom==null?opt:custom;const red=OPT.eal[0]-OPT.eal[m];const cost=OPT.cost[m];const rosi=cost>0?(red-cost)/cost:0;
  $('#invStats').innerHTML=`<div><div class="k">Portfolio cost</div><div class="x" style="${cost>budget?'color:var(--crit)':''}">${inr(cost)}${cost>budget?' · over budget':''}</div></div><div><div class="k">Risk reduction (joint)</div><div class="x" style="color:var(--good)">−${inr(red)} / yr</div></div><div><div class="k">ROSI</div><div class="x">${cost>0?rosi.toFixed(1)+'×':'—'}</div></div><div><div class="k">Residual EAL</div><div class="x">${inr(OPT.eal[m])}</div></div>`;
  const sel=[];for(let c=0;c<NC;c++)if(m>>c&1)sel.push(c);
  const naive=sel.reduce((s,c)=>s+(OPT.eal[0]-OPT.eal[1<<c]),0);const over=red>0?(naive-red)/red:0;
  $('#naive').innerHTML=sel.length>1?`<span aria-hidden="true">≠</span><span>Adding up each control's standalone benefit would claim <b>${inr(naive)}</b>. The joint re-simulation gives <b>${inr(red)}</b>, because ${over>0.005?'controls overlap on the same assets and findings, so the naive sum overstates the benefit by <b>'+pct(over)+'</b>':'these controls barely overlap'}. Suraksha always reports the joint figure.</span>`:`<span aria-hidden="true">i</span><span>Pick two or more controls to see how their combined benefit differs from the sum of their standalone benefits.</span>`;
  // table
  $('#candTbl').innerHTML=`<thead><tr><th></th><th>Control</th><th class="r">Cost</th><th class="r">Standalone reduction</th><th class="r">ROSI</th></tr></thead><tbody>`+CANDIDATES.map((c,i)=>{const on=!!(m>>i&1);const cst=c.capex+c.opex;const r1=OPT.eal[0]-OPT.eal[1<<i];return `<tr><td><input type="checkbox" id="cand-${c.id}" data-c="${i}" ${on?'checked':''} aria-label="Include ${esc(c.name)}"></td><td><label for="cand-${c.id}"><b>${esc(c.name)}</b></label><div class="sub">${c.id} · ${c.cat} · capex ${inr(c.capex)} + opex ${inr(c.opex)}/yr</div></td><td class="r mono">${inr(cst)}</td><td class="r mono">${inr(r1)}</td><td class="r mono">${((r1-cst)/cst).toFixed(1)}×</td></tr>`;}).join('')+'</tbody>';
  renderFrontier(budget,m);
}
function renderFrontier(budget,sel){
  const el=$('#frChart');el.innerHTML='';const W=Math.max(280,el.clientWidth);const H=W<560?270:320;const m={l:W<560?50:60,r:14,t:14,b:32};const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const maxC=Math.max(OPT.cost[NM-1],16e6);let maxR=0;for(let k=0;k<NM;k++)maxR=Math.max(maxR,OPT.eal[0]-OPT.eal[k]);
  const tx=ticks(maxC,4),ty=ticks(maxR*1.05,4);const xmax=tx[tx.length-1],ymax=ty[ty.length-1];
  const xs=v=>m.l+v/xmax*iw,ys=v=>m.t+ih-v/ymax*ih;
  const svg=S('svg',{viewBox:`0 0 ${W} ${H}`,height:H,role:'img','aria-label':'Investment versus risk reduction'},el);
  const fr=frontier();let knee=fr[0];for(let i=1;i<fr.length;i++){const a=fr[i-1],b=fr[i];const slope=((OPT.eal[a]-OPT.eal[b]))/(OPT.cost[b]-OPT.cost[a]);if(slope>=1)knee=b;else break;}
  S('rect',{x:m.l,y:m.t,width:xs(OPT.cost[knee])-m.l,height:ih,style:'fill:var(--good-soft)'},svg);
  const zl=S('text',{x:m.l+6,y:m.t+14,class:'lbl',style:'fill:var(--good)'},svg);zl.textContent='OPTIMAL SPEND ZONE';
  const g=S('g',{class:'ax'},svg);yAxis(g,ys,ty,m.l,m.l+iw,inrAxis);
  tx.forEach(v=>{const t=S('text',{x:xs(v),y:H-10,'text-anchor':v===0?'start':'middle',class:'lbl'},g);t.textContent=inrAxis(v);});
  // break-even line
  const be=Math.min(xmax,ymax);S('line',{x1:xs(0),y1:ys(0),x2:xs(be),y2:ys(be),style:'stroke:var(--muted);stroke-width:1;stroke-dasharray:3 4'},svg);
  const bl=S('text',{x:xs(be)-4,y:ys(be)-6,'text-anchor':'end',class:'lbl'},svg);bl.textContent='break-even';
  for(let k=0;k<NM;k++)S('circle',{cx:xs(OPT.cost[k]),cy:ys(OPT.eal[0]-OPT.eal[k]),r:2.2,style:'fill:var(--ink-2);opacity:.22'},svg);
  let d='';fr.forEach((k,i)=>{const x=xs(OPT.cost[k]),y=ys(OPT.eal[0]-OPT.eal[k]);if(i){const py=ys(OPT.eal[0]-OPT.eal[fr[i-1]]);d+='L'+x+','+py;}d+=(i?'L':'M')+x+','+y;});
  d+='L'+xs(xmax)+','+ys(OPT.eal[0]-OPT.eal[fr[fr.length-1]]);
  S('path',{d,style:'fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round'},svg);
  fr.forEach(k=>S('circle',{cx:xs(OPT.cost[k]),cy:ys(OPT.eal[0]-OPT.eal[k]),r:3.5,style:'fill:var(--s1);stroke:var(--surface);stroke-width:1.5'},svg));
  S('line',{x1:xs(budget),x2:xs(budget),y1:m.t,y2:m.t+ih,style:'stroke:var(--ink);stroke-width:1.5'},svg);
  const blab=S('text',{x:xs(budget)+(xs(budget)>m.l+iw*.7?-6:6),y:m.t+ih-8,'text-anchor':xs(budget)>m.l+iw*.7?'end':'start',class:'dlabel'},svg);blab.textContent='Budget '+inr(budget);
  const sx=xs(OPT.cost[sel]),sy=ys(OPT.eal[0]-OPT.eal[sel]);S('circle',{cx:sx,cy:sy,r:7,style:'fill:var(--s2);stroke:var(--surface);stroke-width:2'},svg);
  const sl=S('text',{x:sx+(sx>m.l+iw*.6?-11:11),y:sy-10,'text-anchor':sx>m.l+iw*.6?'end':'start',class:'dlabel'},svg);sl.textContent='−'+inr(OPT.eal[0]-OPT.eal[sel])+' / yr';
  legend($('#frLegend'),[{t:'Best reachable reduction',c:'var(--s1)',kind:'line'},{t:'Selected portfolio',c:'var(--s2)'},{t:'All 1,024 portfolios',c:'var(--ink-2)'}]);
  const hit=S('rect',{x:m.l,y:m.t,width:iw,height:ih,style:'fill:transparent'},svg);
  hit.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)*(W/r.width);const c=Math.max(0,(px-m.l)/iw*xmax);const b=bestFor(c);const ids=CANDIDATES.filter((q,i)=>b>>i&1).map(q=>q.id).join(', ')||'nothing';
    showTip(`<div class="t">Spend up to ${inr(c)}</div><div class="r"><span>Best portfolio</span><b>${ids}</b></div><div class="r"><span>Cost</span><b>${inr(OPT.cost[b])}</b></div><div class="r"><span>Risk reduction</span><b>${inr(OPT.eal[0]-OPT.eal[b])}</b></div>`,ev);});
  hit.addEventListener('mouseleave',hideTip);
  hit.addEventListener('click',ev=>{const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)*(W/r.width);const c=Math.max(0,Math.min(16e6,(px-m.l)/iw*xmax));$('#budget').value=Math.round(c/25e4)*25e4;custom=null;renderInvest();});
}
$('#budget').addEventListener('input',()=>{custom=null;renderInvest();});
$('#resetOpt').addEventListener('click',()=>{custom=null;renderInvest();});
$('#candTbl').addEventListener('change',e=>{const cb=e.target.closest('input[data-c]');if(!cb||!OPT.ready)return;const cur=custom==null?bestFor(+$('#budget').value):custom;custom=cur^(1<<+cb.dataset.c);renderInvest();});
