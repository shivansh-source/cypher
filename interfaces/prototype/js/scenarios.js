/* What-if scenario lab, re-simulated on the same random draws as the baseline. */
'use strict';
/* ================= scenarios ================= */
function renderScenario(){
  const on={mfa:$('#sc-mfa').checked,kev:$('#sc-kev').checked,edr:$('#sc-edr').checked,delay:$('#sc-delay').checked};
  let st=cloneState(CUR_STATE),P=BASE;
  if(on.mfa)st=applyControls(st,[2]);
  if(on.kev)[...st.open].forEach(s=>{if(FINDINGS[s].kev)st.open.delete(s);});
  if(on.edr)P=withP({edrFail:true});
  const any=on.mfa||on.kev||on.edr;let html;
  if(any){const r=evalState(st,P,true);scenarioTot=r.tot;const v=quant(r.tot,.95);const d=r.eal-CURR.eal;
    html=`<div><div class="k">EAL, what-if</div><div class="x">${inr(r.eal)}</div></div><div><div class="k">Change vs today</div><div class="x" style="color:${d>0?'var(--crit)':'var(--good)'}">${d>0?'+':''}${inr(d)} (${d>0?'+':''}${pct(d/CURR.eal)})</div></div><div><div class="k">VaR 95%, what-if</div><div class="x">${inr(v)}</div></div>`;
  }else{scenarioTot=null;html=`<div><div class="k">EAL today</div><div class="x">${inr(CURR.eal)}</div></div><div><div class="k">VaR 95% today</div><div class="x">${inr(CURR.var)}</div></div><div><div class="k">Pick a change</div><div class="x muted" style="font-size:13px;font-family:var(--sans)">Results appear here</div></div>`;}
  if(on.delay)html+=`<div style="grid-column:1/-1;background:var(--serious-soft)"><div class="k" style="color:var(--serious)">30-day delay</div><div class="x" style="font-size:14px">+${inr(delayCost)} extra expected loss by ${wdate(HORIZON)} as planned fixes slip</div></div>`;
  $('#scResult').innerHTML=html;renderLEC();
}
