/* Sample reference environment: assets, findings, control events and candidate controls. SAMPLE DATA, not a real organization. */
'use strict';
/* ================= reference environment (sample) ================= */
const LOSS_TYPES=['Downtime & interruption','Response & recovery','Data breach','Regulatory penalty','Reputation & churn'];
const ASSETS=[
 {id:'pay-gw-01',name:'Payments gateway',bu:'Payments',crit:'critical',inet:true,ctl:{mfa:false,edr:true,seg:false},backup:'tested',shares:[.45,.15,.10,.20,.10],src:'CMDB AST-0101'},
 {id:'core-lms-db',name:'Loan management DB',bu:'Lending',crit:'critical',inet:false,ctl:{mfa:false,edr:true,seg:false},backup:'untested',shares:[.25,.15,.25,.25,.10],src:'CMDB AST-0144'},
 {id:'kyc-store',name:'KYC document store (S3)',bu:'Lending',crit:'critical',inet:true,ctl:{mfa:false,edr:false,seg:false},backup:'untested',shares:[.05,.15,.35,.35,.10],edrNA:true,src:'CMDB AST-0192'},
 {id:'cust-portal',name:'Customer portal',bu:'Digital',crit:'high',inet:true,ctl:{mfa:false,edr:false,seg:false},backup:'tested',shares:[.15,.15,.30,.25,.15],src:'CMDB AST-0120'},
 {id:'ad-dc-01',name:'Active Directory DC',bu:'Shared IT',crit:'critical',inet:false,ctl:{mfa:false,edr:true,seg:false},backup:'tested',shares:[.45,.30,.10,.05,.10],src:'CMDB AST-0007'},
 {id:'vpn-edge',name:'Remote-access VPN',bu:'Shared IT',crit:'high',inet:true,ctl:{mfa:false,edr:false,seg:false},backup:'tested',shares:[.30,.30,.15,.10,.15],edrNA:true,src:'CMDB AST-0011'},
 {id:'mail-gw',name:'Email gateway',bu:'Shared IT',crit:'high',inet:true,ctl:{mfa:false,edr:false,seg:false},backup:'tested',shares:[.20,.35,.25,.10,.10],src:'CMDB AST-0015'},
 {id:'dev-ci',name:'CI/CD server (Jenkins)',bu:'Engineering',crit:'high',inet:false,ctl:{mfa:false,edr:false,seg:false},backup:'untested',shares:[.30,.40,.15,.05,.10],src:'CMDB AST-0230'},
 {id:'wiki',name:'Intranet wiki',bu:'Corporate',crit:'medium',inet:false,ctl:{mfa:false,edr:false,seg:false},backup:'tested',shares:[.20,.40,.25,.05,.10],src:'CMDB AST-0301'},
 {id:'mkt-site',name:'Marketing website',bu:'Digital',crit:'low',inet:true,ctl:{mfa:false,edr:false,seg:false},backup:'tested',shares:[.15,.35,.05,.05,.40],src:'CMDB AST-0350'},
];
const AB={};ASSETS.forEach(a=>AB[a.id]=a);
const FINDINGS=[
 {id:'F-0877',asset:'cust-portal',title:'Log4Shell in legacy loan-calculator service',short:'Log4Shell · portal',cve:'CVE-2021-44228',epss:.94,kev:true,src:'greenbone',det:0,rem:null,plan:28},
 {id:'F-0791',asset:'ad-dc-01',title:'Netlogon privilege escalation (Zerologon)',short:'Zerologon · AD',cve:'CVE-2020-1472',epss:.94,kev:true,src:'wazuh',det:0,rem:5},
 {id:'F-1042',asset:'vpn-edge',title:'PAN-OS GlobalProtect command injection',short:'PAN-OS · VPN',cve:'CVE-2024-3400',epss:.94,kev:true,src:'greenbone',det:2,rem:9},
 {id:'F-0930',asset:'pay-gw-01',title:'TLS 1.0 still negotiated',short:'TLS 1.0 · payments',cve:null,epss:.01,kev:false,src:'greenbone',det:3,rem:null,plan:31},
 {id:'F-0955',asset:'core-lms-db',title:'MySQL below vendor critical patch level',short:'MySQL CPU · lending DB',cve:null,epss:null,kev:false,src:'greenbone',det:4,rem:null,plan:30},
 {id:'F-1120',asset:'mail-gw',title:'Barracuda ESG remote command injection',short:'Barracuda ESG · mail',cve:'CVE-2023-2868',epss:.93,kev:true,src:'greenbone',det:6,rem:11},
 {id:'F-1177',asset:'wiki',title:'Confluence broken access control',short:'Confluence · wiki',cve:'CVE-2023-22515',epss:.94,kev:true,src:'greenbone',det:8,rem:13},
 {id:'F-1233',asset:'core-lms-db',title:'Database backups stored unencrypted',short:'Unencrypted backups',cve:null,epss:null,kev:false,src:'scoutsuite',det:10,rem:null,plan:32},
 {id:'F-1311',asset:'pay-gw-01',title:'OpenSSH signal-handler race (regreSSHion)',short:'regreSSHion · payments',cve:'CVE-2024-6387',epss:.41,kev:false,src:'greenbone',det:12,rem:null,plan:27},
 {id:'F-1364',asset:'dev-ci',title:'Jenkins CLI arbitrary file read',short:'Jenkins CLI · CI',cve:'CVE-2024-23897',epss:.94,kev:true,src:'wazuh',det:15,rem:null,plan:27},
 {id:'F-1390',asset:'kyc-store',title:'KYC bucket allows public object listing',short:'Public KYC bucket',cve:null,epss:null,misconfig:true,kev:false,src:'prowler',det:16,rem:null,plan:26},
 {id:'F-1402',asset:'mkt-site',title:'PHP-CGI argument injection',short:'PHP-CGI · marketing',cve:'CVE-2024-4577',epss:.94,kev:true,src:'greenbone',det:17,rem:null,plan:29},
 {id:'F-1455',asset:'cust-portal',title:'Apache mod_rewrite source disclosure',short:'Apache · portal',cve:'CVE-2024-38475',epss:.92,kev:true,src:'greenbone',det:19,rem:null,plan:27},
];
ASSETS.forEach(a=>FINDINGS.push({id:'R-'+a.id,asset:a.id,title:'Residual exposure: unknown and unscanned flaws',short:'Residual · '+a.name,cve:null,epss:null,residualP:.06,kev:false,src:'engine',det:0,rem:null,plan:null,residual:true}));
const FIDX={};FINDINGS.forEach((f,i)=>FIDX[f.id]=i);
const isReal=s=>!FINDINGS[s].residual;
const CONTROL_EVENTS=[{w:14,asset:'vpn-edge',ctl:'mfa',val:true},{w:18,asset:'cust-portal',ctl:'edr',val:true}];
const ANN=[{w:5,label:'Zerologon patched'},{w:9,label:'PAN-OS patched'},{w:14,label:'MFA on VPN'},{w:16,label:'Public KYC bucket found'},{w:21,label:'Gate failed · snapshot held',gate:true}];
const CUR=25,HORIZON=33,DELAY=4,GATE_FAIL=21,APPETITE=3e7;
const CANDIDATES=[
 {id:'C1',name:'Patch customer portal (Log4Shell, Apache)',cat:'Patch',capex:6e5,opex:2e5,remove:['F-0877','F-1455']},
 {id:'C2',name:'Patch payments gateway (OpenSSH, TLS 1.0)',cat:'Patch',capex:2.5e5,opex:.5e5,remove:['F-1311','F-0930']},
 {id:'C3',name:'MFA for all privileged accounts',cat:'Identity',capex:18e5,opex:6e5,set:{mfa:['ad-dc-01','pay-gw-01','core-lms-db','dev-ci']}},
 {id:'C4',name:'EDR on remaining servers',cat:'Endpoint',capex:14e5,opex:8e5,set:{edr:['dev-ci','mkt-site','mail-gw','wiki']}},
 {id:'C5',name:'Lock down KYC bucket + CSPM guardrails',cat:'Cloud',capex:3e5,opex:2e5,remove:['F-1390']},
 {id:'C6',name:'Segment lending & payments tiers',cat:'Network',capex:40e5,opex:5e5,set:{seg:['core-lms-db','kyc-store','pay-gw-01']}},
 {id:'C7',name:'Immutable, tested backups (lending, KYC)',cat:'Resilience',capex:24e5,opex:6e5,backup:['core-lms-db','kyc-store'],remove:['F-1233']},
 {id:'C8',name:'Upgrade Jenkins, harden CI',cat:'Patch',capex:3e5,opex:1e5,remove:['F-1364']},
 {id:'C9',name:'Rebuild marketing site off PHP-CGI',cat:'Patch',capex:5e5,opex:1e5,remove:['F-1402']},
 {id:'C10',name:'Database critical patch update',cat:'Patch',capex:1.5e5,opex:.5e5,remove:['F-0955']},
];
