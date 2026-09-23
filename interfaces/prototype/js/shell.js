/* Sidebar collapse state and the snapshot id shown in the sidebar. */
'use strict';
/* sidebar collapse */
const appEl=$('#app'),colBtn=$('#collapseBtn');
function setCollapsed(c,persist){appEl.classList.toggle('collapsed',c);colBtn.setAttribute('aria-expanded',String(!c));colBtn.title=c?'Expand sidebar':'Collapse sidebar';colBtn.querySelector('.t').textContent=c?'Expand sidebar':'Collapse sidebar';
  if(persist){try{localStorage.setItem('suraksha.sidebar',c?'collapsed':'open');}catch(e){}}
  setTimeout(()=>renderView(current),240);}
colBtn.addEventListener('click',()=>setCollapsed(!appEl.classList.contains('collapsed'),true));
try{if(localStorage.getItem('suraksha.sidebar')==='collapsed'){appEl.classList.add('collapsed');colBtn.setAttribute('aria-expanded','false');colBtn.title='Expand sidebar';colBtn.querySelector('.t').textContent='Expand sidebar';}}catch(e){}

/* snapshot id (content hash stand-in) */
let hsh=2166136261;JSON.stringify([FINDINGS,ASSETS]).split('').forEach(c=>{hsh^=c.charCodeAt(0);hsh=Math.imul(hsh,16777619);});
const CURR_ID='sha256:'+((hsh>>>0).toString(16)+'9c2e41d07ab35f18e6c0').slice(0,20)+'…';
$('#snapId').textContent=CURR_ID;
