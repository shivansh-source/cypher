/* Ask Suraksha: routes a question to an engine tool and renders the answer from tool output. It never computes a figure. */
'use strict';
/* ================= Ask ================= */
const PRESETS=[['What is our highest financial cyber risk today?','top1'],['Which vulnerabilities contribute most to expected losses?','top3'],['What happens if MFA is enforced on all privileged accounts?','mfa'],['How does delaying remediation by 30 days affect exposure?','delay'],['What should we fund with ₹1 crore?','opt']];
const V=x=>`<span class="v">${x}</span>`;
function answer(intent){
  const open=[...CUR_STATE.open].filter(isReal).sort((a,b)=>CURR.mean[b]-CURR.mean[a]);let body,tool,n;
  if(intent==='top1'){const s=open[0],f=FINDINGS[s],a=AB[f.asset];body=`Your largest single exposure is <b>${esc(f.title)}</b> on ${esc(a.name)}, carrying ${V(inr(CURR.mean[s]))} of expected annual loss, ${V(pct(CURR.mean[s]/CURR.eal))} of the ${V(inr(CURR.eal))} total.`;tool='get_top_contributors';n=3;}
  else if(intent==='top3'){body='The three largest contributors are:<br>'+open.slice(0,3).map((s,i)=>`${i+1}. ${esc(FINDINGS[s].short)}: ${V(inr(CURR.mean[s]))}`).join('<br>')+`<br>Together, ${V(pct(open.slice(0,3).reduce((t,s)=>t+CURR.mean[s],0)/CURR.eal))} of expected annual loss.`;tool='get_top_contributors';n=4;}
  else if(intent==='mfa'){const r=evalState(applyControls(CUR_STATE,[2]));body=`Re-simulating with MFA on AD, the payments gateway, the lending DB and the CI server moves expected annual loss from ${V(inr(CURR.eal))} to ${V(inr(r.eal))}, a reduction of ${V(inr(CURR.eal-r.eal))}. The estimated first-year cost is ${V(inr(CANDIDATES[2].capex+CANDIDATES[2].opex))}.`;tool='simulate_scenario';n=4;}
  else if(intent==='delay'){body=`If every planned fix slips 30 days, you carry an extra ${V(inr(delayCost))} of expected loss by ${wdate(HORIZON)}. The costliest slip is the public KYC bucket, which accrues ${V(inr(CURR.mean[FIDX['F-1390']]/365))} a day while open.`;tool='simulate_scenario';n=2;}
  else if(intent==='opt'){if(!OPT.ready)return {body:'Portfolio simulation is still running. Ask again in a moment.',tool:'optimize_investment',n:0};const b=bestFor(1e7);const ids=CANDIDATES.filter((c,i)=>b>>i&1).map(c=>c.id);body=`The best portfolio within ₹1 crore is ${ids.join(', ')}, costing ${V(inr(OPT.cost[b]))} and cutting expected annual loss by ${V(inr(OPT.eal[0]-OPT.eal[b]))}. That figure comes from one joint re-simulation of the whole portfolio, not a sum of per-control estimates.`;tool='optimize_investment';n=2;}
  else{body='I can only answer from engine tools: current exposure, top contributors, what-if scenarios, remediation delay, and budget optimization. I won\'t estimate a figure the engine hasn\'t computed.';tool='none (no matching tool)';n=0;}
  return {body,tool,n};
}
function classify(q){q=q.toLowerCase();if(/mfa|multi.?factor|privileged/.test(q))return 'mfa';if(/delay|30 days|postpone|slip/.test(q))return 'delay';if(/fund|budget|crore|invest|spend|optimi/.test(q))return 'opt';if(/which|contribut|most|top/.test(q))return 'top3';if(/highest|biggest|largest|risk today|exposure/.test(q))return 'top1';return 'none';}
function ask(q,intent){const th=$('#thread');const r=answer(intent||classify(q));
  th.insertAdjacentHTML('beforeend',`<div class="q">${esc(q)}</div><div class="a">${r.body}<details class="src"><summary>Source</summary><div class="body"><span>tool: ${r.tool}</span>${r.n?`<span class="ok">✓ ${r.n} figures verified against engine output</span>`:''}<span>snapshot ${CURR_ID.slice(0,15)}…</span></div></details></div>`);th.scrollTop=th.scrollHeight;}
$('#presets').innerHTML=PRESETS.map((p,i)=>`<button type="button" data-p="${i}">${esc(p[0])}</button>`).join('');
$('#presets').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const p=PRESETS[+b.dataset.p];ask(p[0],p[1]);});
$('#askForm').addEventListener('submit',e=>{e.preventDefault();const v=$('#askInput').value.trim();if(!v)return;ask(v);$('#askInput').value='';});

/* ask modal */
const modal=$('#askModal');let lastFocus=null;
function openAsk(){lastFocus=document.activeElement;modal.hidden=false;document.body.classList.add('modal-open');setTimeout(()=>{$('#askInput').focus();const th=$('#thread');th.scrollTop=th.scrollHeight;},30);}
function closeAsk(){modal.hidden=true;document.body.classList.remove('modal-open');hideTip();if(lastFocus&&lastFocus.focus)lastFocus.focus();}
$('#openAsk').addEventListener('click',openAsk);
modal.addEventListener('click',e=>{if(e.target.closest('[data-close]'))closeAsk();});
document.addEventListener('keydown',e=>{
  if(modal.hidden)return;
  if(e.key==='Escape'){e.preventDefault();closeAsk();return;}
  if(e.key==='Tab'){const f=[...modal.querySelectorAll('button,input')].filter(x=>!x.disabled&&x.offsetParent);if(!f.length)return;const first=f[0],last=f[f.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
});
