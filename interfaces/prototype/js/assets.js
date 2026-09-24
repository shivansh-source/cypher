/* Assets view: asset table, FAIR parameter detail and remediation backlog. */
'use strict';
/* ================= Assets view ================= */
let selAsset='kyc-store';
function assetEal(id){let v=0;for(let s=0;s<nS;s++)if(FINDINGS[s].asset===id)v+=CURR.mean[s];return v;}
function ctlChips(id){const c=CUR_STATE.ctl[id],a=AB[id],b=CUR_STATE.backup[id];const ch=(k,on,na)=>`<i class="${na?'na':on?'on':'off'}">${k}</i>`;return `<span class="ctl">${ch('MFA',c.mfa)}${ch('EDR',c.edr,a.edrNA)}${ch('SEG',c.seg)}${ch('BKP',b==='tested')}</span>`;}
function renderAssets(){
  const rows=ASSETS.map(a=>({a,v:assetEal(a.id),n:[...CUR_STATE.open].filter(s=>isReal(s)&&FINDINGS[s].asset===a.id).length})).sort((x,y)=>y.v-x.v);
  $('#assetTbl').innerHTML=`<thead><tr><th>Asset</th><th>Criticality</th><th>Controls</th><th class="r">Open</th><th class="r">EAL</th></tr></thead><tbody>`+rows.map(r=>`<tr class="click ${r.a.id===selAsset?'sel':''}" data-a="${r.a.id}" tabindex="0"><td><b>${esc(r.a.name)}</b><div class="sub mono">${r.a.id} · ${esc(r.a.bu)} · ${r.a.inet?'internet-facing':'internal'}</div></td><td class="crit-${r.a.crit}" style="font-weight:600">${r.a.crit}</td><td>${ctlChips(r.a.id)}</td><td class="r mono">${r.n}</td><td class="r mono">${inr(r.v)}</td></tr>`).join('')+'</tbody>';
  renderAssetDetail();renderBacklog();
}
function renderAssetDetail(){
  const a=AB[selAsset];const fs=FINDINGS.map((f,s)=>({f,s})).filter(x=>x.f.asset===a.id&&!x.f.residual);const rs=FIDX['R-'+a.id];const pr=PROFILE[a.inet?'internet':'internal'];const mp=MAGP[a.crit];const c=CUR_STATE.ctl[a.id];
  const hm=pertMean(...HEALTHP);let R=1;if(c.mfa)R*=1-BASE.mfa*hm;if(c.edr)R*=1-BASE.edr*hm;if(c.seg)R*=1-BASE.seg*hm;R=1-R;
  const mult=BASE.rto[CUR_STATE.backup[a.id]];
  $('#assetDetail').innerHTML=`<div class="detail"><div><div class="eyebrow">${a.id} · ${esc(a.src)}</div><h2 style="margin-top:4px">${esc(a.name)}</h2><p class="small muted" style="margin-top:4px">${esc(a.bu)} · <span class="crit-${a.crit}">${a.crit}</span> · ${a.inet?'internet-facing':'internal'} · backups ${CUR_STATE.backup[a.id]}</p></div>
  <div class="kv"><div><div class="k">Threat events / yr</div><div class="x">${pertMean(...pr).toFixed(2)}</div></div><div><div class="k">Control resistance</div><div class="x">${pct(R)}</div></div><div><div class="k">Loss per event (mean)</div><div class="x">${inr(pertMean(...mp)*mult)}</div></div><div><div class="k">Asset EAL</div><div class="x">${inr(assetEal(a.id))}</div></div><div><div class="k">of which residual</div><div class="x">${inr(CURR.mean[rs])}</div></div></div>
  <div><h3 style="margin-bottom:6px">Findings</h3>${fs.length?`<div class="rank">${fs.map(({f,s})=>{const open=CUR_STATE.open.has(s);const p=exploitP(f,BASE);return `<div class="it" style="grid-template-columns:minmax(0,1fr) auto"><span class="nm">${esc(f.title)}</span><span class="val">${open?inr(CURR.mean[s]):'<span class="pill good">✓ Fixed</span>'}</span><span class="meta" style="grid-column:1/-1">${f.id}${f.cve?' · '+f.cve:''} · exploit p ${p.toFixed(2)}${f.epss==null?' (declared)':' (EPSS)'}${f.kev?' <span class="mini kev">KEV</span>':''} · ${esc(f.src)}_connector · raw:${f.src.slice(0,3)}-${f.id.slice(2)}${open?' · loss events/yr '+(pertMean(...pr)*p*(1-R)).toFixed(3):''}</span></div>`;}).join('')}</div>`:'<p class="muted small">No findings on this asset in the current snapshot.</p>'}</div>
  <p class="small muted">Threat events per year × exploit probability × (1 − resistance) = loss events per year. Each event's cost is drawn from a Beta-PERT range, so the asset EAL above comes from the simulation, not from multiplying these means.</p></div>`;
}
function renderBacklog(){
  const open=[...CUR_STATE.open].filter(isReal).sort((a,b)=>CURR.mean[b]-CURR.mean[a]);
  $('#backlogTbl').innerHTML=`<thead><tr><th>Finding</th><th>Asset</th><th>Signals</th><th class="r">Open for</th><th>Planned fix</th><th class="r">Cost per day</th><th class="r">Accrued so far</th></tr></thead><tbody>`+open.map(s=>{const f=FINDINGS[s];let acc=0;for(let w=f.det;w<=CUR;w++)acc+=HIST[w].mean[s]*WK;const late=f.plan<=CUR+1;return `<tr><td><b>${esc(f.title)}</b><div class="sub mono">${f.id}${f.cve?' · '+f.cve:''} · via ${f.src}</div></td><td>${esc(AB[f.asset].name)}</td><td>${f.epss!=null?`<span class="mini">EPSS ${f.epss.toFixed(2)}</span> `:'<span class="mini">unscored</span> '}${f.kev?'<span class="mini kev">KEV</span>':''}</td><td class="r mono">${(CUR-f.det+1)*7} d</td><td><span class="pill ${late?'warn':'info'}">${wdate(f.plan)}</span></td><td class="r mono">${inr(CURR.mean[s]/365)}</td><td class="r mono">${inr(acc)}</td></tr>`;}).join('')+'</tbody>';
}
$('#assetTbl').addEventListener('click',e=>{const tr=e.target.closest('tr[data-a]');if(!tr)return;selAsset=tr.dataset.a;renderAssets();});
$('#assetTbl').addEventListener('keydown',e=>{if(e.key!=='Enter')return;const tr=e.target.closest('tr[data-a]');if(!tr)return;selAsset=tr.dataset.a;renderAssets();});
