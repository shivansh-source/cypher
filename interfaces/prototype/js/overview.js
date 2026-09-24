/* Overview: KPI strip, loss-over-time hero chart, loss exceedance curve, contributors, accrued-loss chart and business-unit roll-up. */
'use strict';
/* ================= KPIs ================= */
const prevEal=HIST[CUR-13].eal;
function renderKPIs(){
  const d=(CURR.eal-prevEal)/prevEal;const openReal=[...CUR_STATE.open].filter(isReal);const openKev=openReal.filter(s=>FINDINGS[s].kev).length;
  const opt=OPT.ready?OPT.eal[0]-OPT.eal[bestFor(1e7)]:null;const optCost=OPT.ready?OPT.cost[bestFor(1e7)]:null;
  $('#kpis').innerHTML=`
  <div class="kpi"><span class="eyebrow">Expected annual loss</span><span class="v hero num">${inr(CURR.eal)}</span><span class="s"><span class="delta ${d>0?'up':'down'}">${d>0?'▲':'▼'} ${pct(Math.abs(d))}</span> vs 90 days ago</span></div>
  <div class="kpi"><span class="eyebrow">Value at risk · 95%</span><span class="v num">${inr(CURR.var)}</span><span class="s">A 1-in-20 year loss</span></div>
  <div class="kpi"><span class="eyebrow">Exposure vs risk appetite</span><span class="v num">${pct(CURR.eal/APPETITE)}</span><div class="meter" aria-hidden="true"><i style="width:${Math.min(100,CURR.eal/APPETITE*100)}%"></i></div><span class="s">Board appetite ${inr(APPETITE,1)} a year (declared)</span></div>
  <div class="kpi"><span class="eyebrow">Open loss scenarios</span><span class="v num">${openReal.length}</span><span class="s">${openKev} known-exploited (CISA KEV) · plus residual exposure on every asset</span></div>
  <div class="kpi"><span class="eyebrow">Best use of ₹1 Cr</span><span class="v num" style="color:var(--good)">${opt==null?'…':'−'+inr(opt)}</span><span class="s">${opt==null?'Simulating portfolios…':'a year, for '+inr(optCost)+' · ROSI '+((opt-optCost)/optCost).toFixed(1)+'×'}</span></div>`;
}

/* ================= HERO ================= */
let heroMode='vuln',heroMetric='rate';
function heroSeries(){
  let names,cols,rows;
  if(heroMode==='vuln'){
    names=TOP5.map(s=>FINDINGS[s].short).concat(['Other findings & residual']);cols=SLOT.concat(['var(--other)']);
    rows=HIST.map(h=>{const r=TOP5.map(s=>h.mean[s]);let o=0;for(let s=0;s<nS;s++)if(!TOP5.includes(s))o+=h.mean[s];r.push(o);return r;});
  }else if(heroMode==='type'){
    names=LOSS_TYPES.slice();cols=TYPE_COL.slice();
    rows=HIST.map(h=>{const r=[0,0,0,0,0];for(let s=0;s<nS;s++){const sh=AB[FINDINGS[s].asset].shares;for(let t=0;t<5;t++)r[t]+=h.mean[s]*sh[t];}return r;});
  }else{
    names=['Expected annual loss','Value at risk (95%)'];cols=['var(--s1)','var(--s7)'];rows=HIST.map(h=>[h.eal,h.var]);
  }
  if(heroMetric==='accrued'){
    if(heroMode==='total'){names=['Expected loss accrued'];cols=['var(--s1)'];let c=0;rows=HIST.map(h=>{c+=h.eal*WK;return [c];});}
    else{const acc=rows[0].map(()=>0);rows=rows.map(r=>r.map((v,k)=>acc[k]+=v*WK));}
  }
  return {names,cols,rows};
}
function renderHero(){
  const el=$('#heroChart');el.innerHTML='';const W=Math.max(300,el.clientWidth);const mob=W<560;const H=mob?290:360;
  const m={l:mob?54:66,r:mob?10:14,t:40,b:30};const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const {names,cols,rows}=heroSeries();const stacked=heroMode!=='total';
  const acc=heroMetric==='accrued';
  let fcPlan,fcDelay;
  if(acc){let cp=HIST.reduce((s,h)=>s+h.eal*WK,0),cd=cp;fcPlan=[{w:CUR,v:cp}];fcDelay=[{w:CUR,v:cd}];FC.plan.forEach((p,i)=>{cp+=p.eal*WK;cd+=FC.delay[i].eal*WK;fcPlan.push({w:p.w,v:cp});fcDelay.push({w:p.w,v:cd});});}
  else{fcPlan=[{w:CUR,v:CURR.eal}].concat(FC.plan.map(p=>({w:p.w,v:p.eal})));fcDelay=[{w:CUR,v:CURR.eal}].concat(FC.delay.map(p=>({w:p.w,v:p.eal})));}
  let maxV=0;rows.forEach(r=>{const t=stacked?r.reduce((a,b)=>a+b,0):Math.max(...r);maxV=Math.max(maxV,t);});
  fcDelay.forEach(p=>maxV=Math.max(maxV,p.v));fcPlan.forEach(p=>maxV=Math.max(maxV,p.v));
  const tk=ticks(maxV*1.04,mob?4:5);const ymax=tk[tk.length-1];
  const xs=w=>m.l+w/HORIZON*iw,ys=v=>m.t+ih-v/ymax*ih;
  const svg=S('svg',{viewBox:`0 0 ${W} ${H}`,height:H,role:'img','aria-label':$('#heroTitle').textContent},el);
  const defs=S('defs',null,svg);const pat=S('pattern',{id:'hatch',width:6,height:6,patternUnits:'userSpaceOnUse',patternTransform:'rotate(45)'},defs);S('line',{x1:0,y1:0,x2:0,y2:6,style:'stroke:var(--muted);stroke-width:1.2;opacity:.45'},pat);
  // forecast zone
  S('rect',{x:xs(CUR),y:m.t,width:xs(HORIZON)-xs(CUR),height:ih,style:'fill:var(--surface-2)'},svg);
  const fzl=S('text',{x:xs(CUR)+6,y:m.t+ih-8,class:'lbl'},svg);fzl.textContent='FORECAST';
  // gate-held band
  S('rect',{x:xs(GATE_FAIL-.5),y:m.t,width:xs(1)-xs(0),height:ih,fill:'url(#hatch)'},svg);
  const g=S('g',{class:'ax'},svg);yAxis(g,ys,tk,m.l,m.l+iw,inrAxis);
  S('line',{x1:m.l,x2:m.l+iw,y1:ys(0),y2:ys(0),style:'stroke:var(--ink-2);opacity:.5'},g);
  const step=mob?8:4;for(let w=0;w<=HORIZON;w+=step){const t=S('text',{x:xs(w),y:H-10,'text-anchor':w===0?'start':'middle',class:'lbl'},g);t.textContent=wdate(w);}
  // series
  if(stacked){
    const base=HIST.map(()=>0);
    names.forEach((n,k)=>{
      const top=rows.map((r,w)=>base[w]+r[k]);
      let d='M'+xs(0)+','+ys(top[0]);for(let w=1;w<=CUR;w++)d+='L'+xs(w)+','+ys(top[w]);
      for(let w=CUR;w>=0;w--)d+='L'+xs(w)+','+ys(base[w]);d+='Z';
      S('path',{d,style:`fill:${cols[k]};opacity:.88;stroke:var(--surface);stroke-width:1.5;stroke-linejoin:round`},svg);
      top.forEach((v,w)=>base[w]=v);
    });
  }else{
    names.forEach((n,k)=>{let d='';rows.forEach((r,w)=>{d+=(w?'L':'M')+xs(w)+','+ys(r[k]);});
      if(k===0&&!acc){let a=d+'L'+xs(CUR)+','+ys(0)+'L'+xs(0)+','+ys(0)+'Z';S('path',{d:a,style:`fill:${cols[k]};opacity:.1`},svg);}
      S('path',{d,style:`fill:none;stroke:${cols[k]};stroke-width:2;stroke-linejoin:round`},svg);
      const last=rows[CUR][k];const t=S('text',{x:xs(CUR)-6,y:ys(last)-8,'text-anchor':'end',class:'dlabel'},svg);t.textContent=(k===0?'EAL ':'VaR ')+inr(last,1);
    });
  }
  // forecast lines + delay area
  if(!(heroMode==='total'&&false)){
    let a='M'+xs(fcDelay[0].w)+','+ys(fcDelay[0].v);fcDelay.forEach(p=>a+='L'+xs(p.w)+','+ys(p.v));for(let i=fcPlan.length-1;i>=0;i--)a+='L'+xs(fcPlan[i].w)+','+ys(fcPlan[i].v);a+='Z';
    S('path',{d:a,style:'fill:var(--serious);opacity:.14'},svg);
    const line=(pts,col)=>{let d='';pts.forEach((p,i)=>d+=(i?'L':'M')+xs(p.w)+','+ys(p.v));S('path',{d,style:`fill:none;stroke:${col};stroke-width:2;stroke-dasharray:5 4`},svg);};
    line(fcDelay,'var(--serious)');line(fcPlan,'var(--plan)');
    const lp=fcPlan[fcPlan.length-1],ld=fcDelay[fcDelay.length-1];
    const t1=S('text',{x:xs(HORIZON)-4,y:Math.min(ys(ld.v)-8,ys(lp.v)-24),'text-anchor':'end',class:'dlabel',style:'fill:var(--serious)'},svg);t1.textContent='Delay '+inr(ld.v,1);
    const t2=S('text',{x:xs(HORIZON)-4,y:Math.min(ys(0)-6,ys(lp.v)+(acc?16:-8)),'text-anchor':'end',class:'dlabel',style:'fill:var(--plan)'},svg);t2.textContent='Planned '+inr(lp.v,1);
  }
  // annotations
  const ag=S('g',{class:'ann'},svg);
  ANN.forEach((a,i)=>{const x=xs(a.w);const row=i%2;const y=m.t-26+row*13;
    S('line',{x1:x,x2:x,y1:y+3,y2:m.t+ih,style:`stroke:${a.gate?'var(--crit)':'var(--ink-2)'};stroke-width:1;opacity:${a.gate?.7:.35}`},ag);
    S('circle',{cx:x,cy:y+3,r:3,style:`fill:${a.gate?'var(--crit)':'var(--ink-2)'}`},ag);
    const right=x>m.l+iw*.72;const t=S('text',{x:right?x-6:x+6,y:y+7,'text-anchor':right?'end':'start'},ag);t.textContent=mob&&a.label.length>18?a.label.split(' ·')[0]:a.label;
  });
  // crosshair
  const ch=S('line',{y1:m.t,y2:m.t+ih,style:'stroke:var(--ink);stroke-width:1;opacity:0'},svg);
  const hit=S('rect',{x:m.l,y:m.t,width:iw,height:ih,style:'fill:transparent;cursor:crosshair'},svg);
  hit.addEventListener('mousemove',ev=>{
    const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)*(W/r.width);const w=Math.max(0,Math.min(HORIZON,Math.round((px-m.l)/iw*HORIZON)));
    ch.setAttribute('x1',xs(w));ch.setAttribute('x2',xs(w));ch.style.opacity=.35;
    let h=`<div class="t">Week of ${wdateY(w)}</div>`;
    if(w<=CUR){
      const r0=rows[w];const order=stacked?names.map((n,k)=>k).reverse():names.map((n,k)=>k);
      order.forEach(k=>{h+=`<div class="r"><span><i class="sw" style="background:${cols[k]}"></i>${esc(names[k])}</span><b>${inr(r0[k])}</b></div>`;});
      if(stacked)h+=`<div class="r tot"><span>Total${acc?' accrued':' EAL'}</span><b>${inr(r0.reduce((a,b)=>a+b,0))}</b></div>`;
      if(HIST[w].held)h+=`<div class="r tot" style="color:var(--crit)"><span>Candidate failed a quality gate; previous snapshot held</span></div>`;
    }else{
      const i=w-CUR;h+=`<div class="r"><span><i class="sw" style="background:var(--plan)"></i>Planned fixes</span><b>${inr(fcPlan[i].v)}</b></div><div class="r"><span><i class="sw" style="background:var(--serious)"></i>30-day delay</span><b>${inr(fcDelay[i].v)}</b></div><div class="r tot"><span>Cost of delay</span><b>${inr(fcDelay[i].v-fcPlan[i].v)}</b></div>`;
    }
    showTip(h,ev);
  });
  hit.addEventListener('mouseleave',()=>{ch.style.opacity=0;hideTip();});
  // legend + titles
  const items=names.map((n,k)=>({t:n,c:cols[k],kind:stacked?'':'line'}));
  items.push({t:'Planned fixes',c:'var(--plan)',kind:'dash'},{t:'30-day delay',c:'var(--serious)',kind:'dash'});
  legend($('#heroLegend'),items);
  $('#heroTitle').textContent=(acc?'Expected loss accrued over time':'Expected annual loss over time')+(heroMode==='vuln'?', by vulnerability':heroMode==='type'?', by loss type':'');
  $('#heroSub').textContent=heroMode==='total'?(acc?'Running total of expected loss since April, from every weekly snapshot.':'Mean annual loss and the 1-in-20 year tail, re-simulated for every weekly snapshot.'):'Each weekly snapshot is re-simulated in full. Shaded bands show what drives loss; dashed lines project the next 8 weeks with planned fixes versus a 30-day delay.';
  const lp=FC.plan[FC.plan.length-1].eal;
  $('#heroFoot').innerHTML=`<span>Cost of a 30-day remediation delay: <b>${inr(delayCost)}</b> extra expected loss by ${wdate(HORIZON)}</span><span>Planned fixes take EAL from <b>${inr(CURR.eal,1)}</b> to <b>${inr(lp,1)}</b></span><span class="muted">Hatched week: candidate snapshot rejected (scanner unreachable)</span>`;
}

/* ================= LEC ================= */
let scenarioTot=null;
function lecPoints(tot){const a=Float64Array.from(tot).sort();const pts=[];const lo=Math.log10(1e6),hi=Math.log10(3e9);for(let i=0;i<=60;i++){const x=Math.pow(10,lo+(hi-lo)*i/60);let k=0,j=a.length;while(k<j){const mid=(k+j)>>1;if(a[mid]<=x)k=mid+1;else j=mid;}pts.push([x,(a.length-k)/a.length]);}return pts;}
function renderLEC(){
  const el=$('#lecChart');el.innerHTML='';const W=Math.max(280,el.clientWidth);const H=W<560?250:290;const m={l:44,r:14,t:14,b:30};const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const lo=Math.log10(1e6),hi=Math.log10(3e9);const xs=v=>m.l+(Math.log10(Math.max(v,1e6))-lo)/(hi-lo)*iw,ys=p=>m.t+ih-p*ih;
  const svg=S('svg',{viewBox:`0 0 ${W} ${H}`,height:H,role:'img','aria-label':'Loss exceedance curve'},el);
  const g=S('g',{class:'ax'},svg);yAxis(g,ys,[0,.25,.5,.75,1],m.l,m.l+iw,v=>pct(v));
  [1e6,1e7,1e8,1e9].forEach(v=>{const t=S('text',{x:xs(v),y:H-10,'text-anchor':v===1e6?'start':'middle',class:'lbl'},g);t.textContent=inrAxis(v);S('line',{x1:xs(v),x2:xs(v),y1:m.t,y2:m.t+ih,class:'grid-l'},g);});
  const draw=(pts,col,fill)=>{let d='';pts.forEach((p,i)=>d+=(i?'L':'M')+xs(p[0])+','+ys(p[1]));if(fill)S('path',{d:d+`L${xs(pts[pts.length-1][0])},${ys(0)}L${xs(pts[0][0])},${ys(0)}Z`,style:`fill:${col};opacity:.1`},svg);S('path',{d,style:`fill:none;stroke:${col};stroke-width:2`},svg);return pts;};
  const base=draw(lecPoints(CURR.tot),'var(--s1)',true);let sc=null;
  if(scenarioTot)sc=draw(lecPoints(scenarioTot),'var(--s3)',false);
  // markers
  const mk=(v,label,col,dy)=>{S('line',{x1:xs(v),x2:xs(v),y1:m.t,y2:m.t+ih,style:`stroke:${col};stroke-width:1;opacity:.7`},svg);const r=xs(v)>m.l+iw*.7;const t=S('text',{x:xs(v)+(r?-5:5),y:m.t+12+dy,'text-anchor':r?'end':'start',class:'dlabel'},svg);t.textContent=label;};
  mk(CURR.eal,'EAL '+inr(CURR.eal,1),'var(--ink-2)',0);mk(CURR.var,'VaR 95% '+inr(CURR.var,1),'var(--s7)',16);
  legend($('#lecLegend'),[{t:'Current snapshot',c:'var(--s1)',kind:'line'}].concat(scenarioTot?[{t:'With what-if changes',c:'var(--s3)',kind:'line'}]:[]));
  const hit=S('rect',{x:m.l,y:m.t,width:iw,height:ih,style:'fill:transparent;cursor:crosshair'},svg);
  const dot=S('circle',{r:4,style:'fill:var(--s1);stroke:var(--surface);stroke-width:2;opacity:0'},svg);
  hit.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)*(W/r.width);let i=Math.round((px-m.l)/iw*60);i=Math.max(0,Math.min(60,i));const p=base[i];dot.setAttribute('cx',xs(p[0]));dot.setAttribute('cy',ys(p[1]));dot.style.opacity=1;
    let h=`<div class="t">Loss above ${inr(p[0])}</div><div class="r"><span><i class="sw" style="background:var(--s1)"></i>Current</span><b>${pct(p[1],1)} chance</b></div>`;if(sc)h+=`<div class="r"><span><i class="sw" style="background:var(--s3)"></i>What-if</span><b>${pct(sc[i][1],1)} chance</b></div>`;showTip(h,ev);});
  hit.addEventListener('mouseleave',()=>{dot.style.opacity=0;hideTip();});
}

/* ================= contributors, BU, accrued ================= */
function renderTop(){
  const open=[...CUR_STATE.open].filter(isReal).sort((a,b)=>CURR.mean[b]-CURR.mean[a]).slice(0,6);const mx=CURR.mean[open[0]];
  $('#topList').innerHTML=open.map((s,i)=>{const f=FINDINGS[s],a=AB[f.asset];return `<div class="it"><span class="n">${i+1}</span><span class="nm"><i class="sw" style="background:${colorOfF(s)};margin-right:6px;vertical-align:-1px"></i>${esc(f.title)}</span><span class="val">${inr(CURR.mean[s])}</span>
  <span class="meta">${esc(a.name)} · <span class="crit-${a.crit}">${a.crit}</span>${f.cve?` · <span class="mini">${f.cve}</span>`:''}${f.epss!=null?` <span class="mini">EPSS ${f.epss.toFixed(2)}</span>`:''}${f.kev?' <span class="mini kev">KEV</span>':''} · ${pct(CURR.mean[s]/CURR.eal)} of EAL</span>
  <div class="bar"><i style="width:${CURR.mean[s]/mx*100}%;background:${colorOfF(s)}"></i></div></div>`;}).join('');
}
function renderBU(){
  const bu={};ASSETS.forEach(a=>bu[a.bu]=0);for(let s=0;s<nS;s++)bu[AB[FINDINGS[s].asset].bu]+=CURR.mean[s];
  const arr=Object.entries(bu).sort((a,b)=>b[1]-a[1]);const mx=arr[0][1];
  $('#buBars').innerHTML=arr.map(([k,v])=>`<div class="hb"><span>${esc(k)}</span><div class="tr"><i style="width:${v/mx*100}%"></i></div><span class="num">${inr(v)}</span></div>`).join('')+`<p class="small muted" style="margin-top:4px">Shares of total: ${arr.map(([k,v])=>esc(k)+' '+pct(v/CURR.eal)).join(' · ')}</p>`;
}
function renderAccrued(){
  const el=$('#accChart');el.innerHTML='';const W=Math.max(280,el.clientWidth);const H=W<560?240:270;const m={l:W<560?50:58,r:14,t:12,b:30};const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const open=[...CUR_STATE.open].filter(isReal);const series=open.map(s=>{const f=FINDINGS[s];let c=0;const pts=[[0,0]];for(let w=f.det;w<=CUR;w++){c+=HIST[w].mean[s]*WK;pts.push([w-f.det+1,c]);}return {s,pts,last:c};}).sort((a,b)=>b.last-a.last);
  const maxX=Math.max(...series.map(x=>x.pts.length-1));const maxY=Math.max(...series.map(x=>x.last));const tk=ticks(maxY*1.05,4);const ymax=tk[tk.length-1];
  const xs=x=>m.l+x/maxX*iw,ys=v=>m.t+ih-v/ymax*ih;
  const svg=S('svg',{viewBox:`0 0 ${W} ${H}`,height:H,role:'img','aria-label':'Accrued expected loss per open finding'},el);
  const g=S('g',{class:'ax'},svg);yAxis(g,ys,tk,m.l,m.l+iw,inrAxis);
  for(let x=0;x<=maxX;x+=5){const t=S('text',{x:xs(x),y:H-10,'text-anchor':x===0?'start':'middle',class:'lbl'},g);t.textContent=x===0?'Detected':x+' wk';}
  series.slice().reverse().forEach(sr=>{let d='';sr.pts.forEach((p,i)=>d+=(i?'L':'M')+xs(p[0])+','+ys(p[1]));const col=colorOfF(sr.s);S('path',{d,style:`fill:none;stroke:${col};stroke-width:2;stroke-linejoin:round`},svg);const lp=sr.pts[sr.pts.length-1];S('circle',{cx:xs(lp[0]),cy:ys(lp[1]),r:4,style:`fill:${col};stroke:var(--surface);stroke-width:2`},svg);});
  series.slice(0,2).forEach(sr=>{const lp=sr.pts[sr.pts.length-1];const r=xs(lp[0])>m.l+iw*.6;const t=S('text',{x:xs(lp[0])+(r?-8:8),y:ys(lp[1])+4,'text-anchor':r?'end':'start',class:'dlabel'},svg);t.textContent=inr(lp[1]);});
  const hit=S('rect',{x:m.l,y:m.t,width:iw,height:ih,style:'fill:transparent;cursor:crosshair'},svg);
  hit.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)*(W/r.width);const x=Math.max(0,Math.min(maxX,Math.round((px-m.l)/iw*maxX)));
    let h=`<div class="t">${x} week${x===1?'':'s'} after detection</div>`;series.forEach(sr=>{const p=sr.pts[Math.min(x,sr.pts.length-1)];const past=x>sr.pts.length-1;h+=`<div class="r"><span><i class="sw" style="background:${colorOfF(sr.s)}"></i>${esc(FINDINGS[sr.s].short)}</span><b>${inr(p[1])}${past?' · today':''}</b></div>`;});showTip(h,ev);});
  hit.addEventListener('mouseleave',hideTip);
  legend($('#accLegend'),series.slice(0,5).map(sr=>({t:FINDINGS[sr.s].short,c:colorOfF(sr.s),kind:'line'})).concat(series.length>5?[{t:'Others',c:'var(--other)',kind:'line'}]:[]));
}
