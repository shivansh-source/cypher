/* Date, rupee and axis formatting helpers. */
'use strict';
/* ================= formatting ================= */
const W0=Date.UTC(2026,2,30);
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const wdate=w=>{const d=new Date(W0+w*7*864e5);return d.getUTCDate()+' '+MON[d.getUTCMonth()];};
const wdateY=w=>{const d=new Date(W0+w*7*864e5);return d.getUTCDate()+' '+MON[d.getUTCMonth()]+' '+d.getUTCFullYear();};
function inr(v,dp){
  if(v==null||!isFinite(v))return '—';
  const a=Math.abs(v),sg=v<0?'−':'';
  if(a>=1e7)return sg+'₹'+(a/1e7).toFixed(dp==null?2:dp)+' Cr';
  if(a>=1e5)return sg+'₹'+(a/1e5).toFixed(dp==null?1:dp)+' L';
  return sg+'₹'+Math.round(a).toLocaleString('en-IN');
}
const trim=x=>String(+x.toFixed(2));
function inrAxis(v){
  if(v===0)return '₹0';const a=Math.abs(v);
  if(a>=1e7)return '₹'+trim(v/1e7)+' Cr';
  if(a>=1e5)return '₹'+trim(v/1e5)+' L';
  return '₹'+trim(v/1e3)+'k';
}
const pct=(x,dp=0)=>(x*100).toFixed(dp)+'%';
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function niceStep(x){const p=Math.pow(10,Math.floor(Math.log10(x)));const f=x/p;return (f<1.5?1:f<3?2:f<7?5:10)*p;}
function ticks(max,n){const st=niceStep(max/n);const out=[];for(let v=0;v<=max+1e-9;v+=st)out.push(v);if(out[out.length-1]<max)out.push(out[out.length-1]+st);return out;}
