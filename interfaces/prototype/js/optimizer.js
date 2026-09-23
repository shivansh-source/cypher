/* Budget optimizer. Every one of the 1,024 candidate portfolios is re-simulated jointly; per-control deltas are never summed (conflict C4). */
'use strict';
/* ================= Optimizer ================= */
const NC=CANDIDATES.length,NM=1<<NC;const OPT={cost:new Float64Array(NM),eal:new Float64Array(NM),ready:false};
function bestFor(budget){let best=0;for(let m=0;m<NM;m++){if(OPT.cost[m]<=budget+1e-6&&(OPT.eal[m]<OPT.eal[best]-1e-6||(Math.abs(OPT.eal[m]-OPT.eal[best])<1e-6&&OPT.cost[m]<OPT.cost[best])))best=m;}return best;}
let custom=null;
function runOptimizer(done){let m=0;function chunk(){const end=Math.min(NM,m+40);for(;m<end;m++){const idx=[];let cost=0;for(let c=0;c<NC;c++)if(m>>c&1){idx.push(c);cost+=CANDIDATES[c].capex+CANDIDATES[c].opex;}OPT.cost[m]=cost;OPT.eal[m]=evalState(applyControls(CUR_STATE,idx)).eal;}const l=$('#optLoading');if(l)l.textContent='Simulating portfolios… '+Math.round(m/NM*100)+'%';if(m<NM)setTimeout(chunk,0);else{OPT.ready=true;done();}}chunk();}
function frontier(){const idx=[...Array(NM).keys()].sort((a,b)=>OPT.cost[a]-OPT.cost[b]);const out=[];let best=-1;idx.forEach(m=>{const red=OPT.eal[0]-OPT.eal[m];if(red>best+1e-6){out.push(m);best=red;}});return out;}
