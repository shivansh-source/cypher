/* Open FAIR + Monte Carlo engine. Deterministic seed, Beta-PERT factors, Poisson event counts and shared control-health factors (conflict C3). Also builds the weekly snapshot history and 8-week forecast. */
'use strict';
/* ================= engine: Open FAIR + Monte Carlo ================= */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
const rng=mulberry32(20260921);
function normal(){let u=0;while(u===0)u=rng();const v=rng();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
function gamma(k){if(k<1)return gamma(k+1)*Math.pow(rng(),1/k);const d=k-1/3,c=1/Math.sqrt(9*d);for(;;){let x,v;do{x=normal();v=1+c*x;}while(v<=0);v=v*v*v;const u=rng();if(u<1-.0331*x*x*x*x)return d*v;if(Math.log(u)<.5*x*x+d*(1-v+Math.log(v)))return d*v;}}
function beta(a,b){const x=gamma(a),y=gamma(b);return x/(x+y);}
function pert(mn,md,mx){const L=4;const a=1+L*(md-mn)/(mx-mn),b=1+L*(mx-md)/(mx-mn);return mn+beta(a,b)*(mx-mn);}
const pertMean=(mn,md,mx)=>(mn+4*md+mx)/6;

const ITER=4000,K=5,nS=FINDINGS.length;
const PROFILE={internet:[.3,1.2,4],internal:[.05,.3,1.2]};
const MAGP={critical:[4e6,1.5e7,1.2e8],high:[8e5,4e6,3e7],medium:[1.5e5,8e5,6e6],low:[3e4,2e5,1.5e6]};
const HEALTHP=[.55,.95,1];
const TEF=new Float32Array(nS*ITER),UC=new Float32Array(nS*ITER),MAG=new Float32Array(nS*ITER*K);
FINDINGS.forEach((f,s)=>{const a=AB[f.asset];const pr=PROFILE[a.inet?'internet':'internal'];const mp=MAGP[a.crit];
  for(let i=0;i<ITER;i++){TEF[s*ITER+i]=pert(pr[0],pr[1],pr[2]);UC[s*ITER+i]=rng();const mb=(s*ITER+i)*K;for(let j=0;j<K;j++)MAG[mb+j]=pert(mp[0],mp[1],mp[2]);}});
const HEALTH={};['mfa','edr','seg'].forEach(c=>{const h=new Float32Array(ITER);for(let i=0;i<ITER;i++)h[i]=pert(HEALTHP[0],HEALTHP[1],HEALTHP[2]);HEALTH[c]=h;});

const BASE={tef:1,magCrit:1,mfa:.4,edr:.5,seg:.35,kevFloor:.5,unscored:.05,misconfigP:.2,rto:{tested:1,untested:1.6,none:2.5},edrFail:false};
function withP(o){return Object.assign({},BASE,o,{rto:Object.assign({},BASE.rto,(o&&o.rto)||{})});}
const exploitP=(f,P)=>{let p=f.residual?f.residualP:f.epss!=null?f.epss:(f.misconfig?P.misconfigP:P.unscored);if(f.kev)p=Math.max(p,P.kevFloor);return p;};

function baseState(){const ctl={},backup={};ASSETS.forEach(a=>{ctl[a.id]=Object.assign({},a.ctl);backup[a.id]=a.backup;});return {open:new Set(),ctl,backup};}
function cloneState(st){const ctl={};for(const k in st.ctl)ctl[k]=Object.assign({},st.ctl[k]);return {open:new Set(st.open),ctl,backup:Object.assign({},st.backup)};}
function stateAt(w,mode){
  const st=baseState();CONTROL_EVENTS.forEach(e=>{if(e.w<=w)st.ctl[e.asset][e.ctl]=e.val;});
  FINDINGS.forEach((f,i)=>{if(f.residual){st.open.add(i);return;}if(f.det>w)return;let end=f.rem;if(end==null&&w>CUR)end=mode==='delay'?f.plan+DELAY:f.plan;if(end==null||end>w)st.open.add(i);});
  return st;
}
function evalState(st,P,wantTot){
  P=P||BASE;const mean=new Float64Array(nS);const tot=wantTot?new Float64Array(ITER):null;
  st.open.forEach(s=>{
    const f=FINDINGS[s],a=AB[f.asset],c=st.ctl[f.asset];const p=exploitP(f,P);
    const cs=[];if(c.mfa)cs.push([P.mfa,HEALTH.mfa]);if(c.edr&&!P.edrFail)cs.push([P.edr,HEALTH.edr]);if(c.seg)cs.push([P.seg,HEALTH.seg]);
    const mult=P.rto[st.backup[f.asset]]*(a.crit==='critical'?P.magCrit:1);const kk=P.tef*p;const b=s*ITER;let sum=0;
    for(let i=0;i<ITER;i++){
      let keep=1;for(let q=0;q<cs.length;q++)keep*=1-cs[q][0]*cs[q][1][i];
      const lam=TEF[b+i]*kk*keep;const u=UC[b+i];let n=0;
      if(lam>0){let pr=Math.exp(-lam),cd=pr;while(u>cd&&n<K){n++;pr*=lam/n;cd+=pr;}}
      if(n){let L=0;const mb=(b+i)*K;for(let j=0;j<n;j++)L+=MAG[mb+j];L*=mult;sum+=L;if(tot)tot[i]+=L;}
    }
    mean[s]=sum/ITER;
  });
  let eal=0;for(let s=0;s<nS;s++)eal+=mean[s];
  return {mean,eal,tot};
}
function quant(tot,q){const a=Float64Array.from(tot).sort();return a[Math.min(a.length-1,Math.floor(q*a.length))];}
function applyControls(st,idxs){const n=cloneState(st);idxs.forEach(ci=>{const c=CANDIDATES[ci];(c.remove||[]).forEach(fid=>n.open.delete(FIDX[fid]));if(c.set)for(const k in c.set)c.set[k].forEach(aid=>n.ctl[aid][k]=true);(c.backup||[]).forEach(aid=>n.backup[aid]='tested');});return n;}

/* history, current, forecast */
const HIST=[];
for(let w=0;w<=CUR;w++){
  if(w===GATE_FAIL){HIST.push(Object.assign({},HIST[w-1],{held:true}));continue;}
  const r=evalState(stateAt(w),BASE,true);HIST.push({mean:r.mean,eal:r.eal,var:quant(r.tot,.95),tot:w===CUR?r.tot:null});
}
const CURR=HIST[CUR];const CUR_STATE=stateAt(CUR);
const FC={plan:[],delay:[]};
for(let w=CUR+1;w<=HORIZON;w++){FC.plan.push({w,eal:evalState(stateAt(w,'plan')).eal});FC.delay.push({w,eal:evalState(stateAt(w,'delay')).eal});}
const WK=7/365;
const delayCost=FC.delay.reduce((s,d,i)=>s+(d.eal-FC.plan[i].eal)*WK,0);

/* vulnerability colour identity: top 5 by loss contributed over history */
const cumByF=new Float64Array(nS);HIST.forEach(h=>{for(let s=0;s<nS;s++)cumByF[s]+=h.mean[s];});
const TOP5=[...Array(nS).keys()].filter(isReal).sort((a,b)=>cumByF[b]-cumByF[a]).slice(0,5);
const SLOT=['var(--s1)','var(--s2)','var(--s3)','var(--s4)','var(--s5)'];
const TYPE_COL=['var(--s1)','var(--s2)','var(--s3)','var(--s4)','var(--s5)'];
const colorOfF=s=>{const k=TOP5.indexOf(s);return k>=0?SLOT[k]:'var(--other)';};
