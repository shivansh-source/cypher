/* View routing and page wiring. Loaded last. */
'use strict';
/* ================= views & wiring ================= */
const rendered={};
function renderView(v){
  if(v==='overview'){renderKPIs();renderHero();renderLEC();renderTop();renderAccrued();renderBU();}
  rendered[v]=true;
}
let current='overview';
function go(v){
  if(!document.getElementById('view-'+v))v='overview';current=v;
  $$('.view').forEach(s=>s.hidden=s.id!=='view-'+v);
  $$('.nav button').forEach(b=>b.setAttribute('aria-current',b.dataset.view===v?'page':'false'));
  const sec=$('#view-'+v);$('#viewTitle').innerHTML=sec.dataset.title;$('#viewEyebrow').textContent=sec.dataset.eyebrow;
  try{history.replaceState(null,'','#'+v);}catch(e){}
  renderView(v);window.scrollTo({top:0});
}
$$('.nav button').forEach(b=>b.addEventListener('click',()=>go(b.dataset.view)));
$$('[data-goto]').forEach(b=>b.addEventListener('click',()=>go(b.dataset.goto)));
$$('[data-hero-mode]').forEach(b=>b.addEventListener('click',()=>{heroMode=b.dataset.heroMode;$$('[data-hero-mode]').forEach(x=>x.setAttribute('aria-pressed',x===b));renderHero();}));
$$('[data-hero-metric]').forEach(b=>b.addEventListener('click',()=>{heroMetric=b.dataset.heroMetric;$$('[data-hero-metric]').forEach(x=>x.setAttribute('aria-pressed',x===b));renderHero();}));
['sc-mfa','sc-kev','sc-edr','sc-delay'].forEach(id=>$('#'+id).addEventListener('change',renderScenario));
let rt;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(()=>renderView(current),120);});

const start=(location.hash||'').replace('#','')||'overview';
go(start);renderScenario();
ask(PRESETS[0][0],PRESETS[0][1]);
runOptimizer(()=>{if(current==='overview')renderKPIs();});
