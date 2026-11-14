import source from '../data/benchmark.json';
export type System = {id:string;name:string;model:string;revision:string;precision:string;policy:string;sampling:string;window:string;hardware:string;warm_state:string;budget:string;sensor_track:string};
export type Resource = {at_ms:number;rss_mb:number|null;queue_depth:number|null;dropped:number|null;age_ms:number|null;scope:string};
export type Row = {task_id:string;session_id:string;system_id:string;suite:string;dataset:string;sensor_track:string;evidence:string;duration_ms:number;event_duration_ms:number;deadline_ms:number;available_ms:number;query_ms:number;answer_ready_ms:number|null;context_ready_ms:number|null;latency_ms:number;context_latency_ms:number|null;success:boolean;quality:number;status:string;early:boolean;correct_facts:number;critical_facts:number;unsupported_claims:number;claim_count:number;false_alerts:number;abstained:boolean;answerable:boolean;stale_error:boolean;cost_usd:number|null;vlm_cost_usd:number|null;calls:number;resources:Resource[];timeline:{type:string;received_ms:number;label:string}[];trace_sha256:string};
export type Comparison={baseline:string;candidate:string;point:Record<string,number|null>;ci95:Record<string,number[]|null>;gates:Record<string,boolean>;status:string;clusters:number};
export type Report={schema_version:number;release:string;experiment_id:string;plan_sha256:string;evidence:string;provenance:string;protocol:string;hardware:string;consumer:string;systems:System[];rows:Row[];comparisons:Comparison[];official_scores:{metric:string;split:string;evaluation_mode:string;benchmark:string;system_id:string;score:number;scale:number;source_url:string;protocol_revision:string}[];acceptance:string};
export const data = source as Report;
export const suites:Record<string,{name:string;short:string;description:string}>={transient:{name:'Brief events',short:'Transient',description:'Catch brief, consequential changes before the evidence disappears.'},semantic:{name:'Subtle semantic changes',short:'Semantic',description:'Read small OCR and state changes without chasing irrelevant motion.'},memory:{name:'State & object memory',short:'Memory',description:'Separate currently visible from last seen and unknown.'},revision:{name:'Audio–visual revisions',short:'Revision',description:'Preserve corrections and align observations across modalities.'},retention:{name:'Query-independent retention',short:'Retention',description:'Keep useful evidence before a future question is known.'},resilience:{name:'Runtime resilience',short:'Resilience',description:'Handle gaps, overload, reset and late completions honestly.'}};
export const colors:Record<string,string>={A:'#c49858',B:'#4c9998',C:'#7855d7',D:'#8a94b3'};
export type Filters={query:string;selected:string[];suite:string;dataset:string;hardware:string;policy:string;sensor:string;evidence:string;budget:string;duration:string;deadline:number};
export const defaults:Filters={query:'',selected:[],suite:'all',dataset:'all',hardware:'all',policy:'all',sensor:'all',evidence:'all',budget:'all',duration:'all',deadline:2000};
export const mean=(values:number[])=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
export const quantile=(values:number[],p:number)=>values.length?[...values].sort((a,b)=>a-b)[Math.max(0,Math.ceil(values.length*p)-1)]:null;
export const fraction=(a:number,b:number)=>b?a/b:null;
export function summarize(rows:Row[],deadline=2000){
 const hours=rows.reduce((s,r)=>s+r.duration_ms,0)/3600000;
 const cost=rows.length&&rows.every(r=>r.cost_usd!==null)?rows.reduce((s,r)=>s+r.cost_usd!,0):null;
 const resources=rows.flatMap(r=>r.resources).map(p=>p.rss_mb).filter((n):n is number=>n!==null);
 return {n:rows.length,hours,cost,costHour:cost===null?null:fraction(cost,hours),success:mean(rows.map(r=>Number(r.quality>0&&r.latency_ms<=deadline))),quality:mean(rows.map(r=>r.quality)),p95:quantile(rows.map(r=>r.latency_ms),.95),p50:quantile(rows.map(r=>r.latency_ms),.5),contextP95:quantile(rows.flatMap(r=>r.context_latency_ms===null?[]:[r.context_latency_ms]),.95),critical:fraction(rows.reduce((s,r)=>s+r.correct_facts,0),rows.reduce((s,r)=>s+r.critical_facts,0)),unsupported:fraction(rows.reduce((s,r)=>s+r.unsupported_claims,0),rows.reduce((s,r)=>s+r.claim_count,0)),stale:mean(rows.map(r=>Number(r.stale_error))),abstain:mean(rows.map(r=>Number(r.abstained))),falseAlerts:fraction(rows.reduce((s,r)=>s+r.false_alerts,0),hours),peak:resources.length?Math.max(...resources):null,calls:rows.reduce((s,r)=>s+r.calls,0),failures:rows.filter(r=>r.status!=='success').length};
}
export const inDuration=(r:Row,duration:string)=>duration==='all'||(duration==='short'?r.event_duration_ms<=500:duration==='medium'?r.event_duration_ms>500&&r.event_duration_ms<=2000:r.event_duration_ms>2000);
export function filterRows(f:Filters,selection=true){
 const systems=data.systems.filter(s=>(!selection||!f.selected.length||f.selected.includes(s.id))&&(f.hardware==='all'||s.hardware===f.hardware)&&(f.policy==='all'||s.policy===f.policy)&&(s.name+' '+s.model).toLowerCase().includes(f.query.toLowerCase()));
 const rows=data.rows.filter(r=>systems.some(s=>s.id===r.system_id)&&(f.suite==='all'||r.suite===f.suite)&&(f.dataset==='all'||r.dataset===f.dataset)&&(f.sensor==='all'||r.sensor_track===f.sensor)&&(f.evidence==='all'||r.evidence===f.evidence)&&inDuration(r,f.duration));
 if(f.budget==='all')return rows;
 const allowed=systems.filter(s=>{const v=summarize(rows.filter(r=>r.system_id===s.id)).costHour;return v!==null&&v<=Number(f.budget);}).map(s=>s.id);
 return rows.filter(r=>allowed.includes(r.system_id));
}
export function pareto(systems:{id:string;cost:number|null;success:number|null}[]){return systems.filter(a=>a.cost!==null&&a.success!==null&&!systems.some(b=>b.id!==a.id&&b.cost!==null&&b.success!==null&&b.cost<=a.cost!&&b.success>=a.success!&&(b.cost<a.cost!||b.success>a.success!))).map(s=>s.id);}
export function readFilters(search:string):Filters{
 const p=new URLSearchParams(search),f={...defaults};
 f.query=p.get('q')??'';f.selected=(p.get('systems')??'').split(',').filter(id=>data.systems.some(s=>s.id===id));
 const options:Record<string,string[]>={suite:Object.keys(suites),dataset:[...new Set(data.rows.map(r=>r.dataset))],hardware:[...new Set(data.systems.map(s=>s.hardware))],policy:[...new Set(data.systems.map(s=>s.policy))],sensor:[...new Set(data.rows.map(r=>r.sensor_track))],evidence:['synthetic','measured'],budget:['0.5','1','2','4'],duration:['short','medium','long']};
 for(const [key,values] of Object.entries(options)){const v=p.get(key);if(v&&values.includes(v))Object.assign(f,{[key]:v});}
 const d=Number(p.get('deadline'));if(d>=250&&d<=10000&&d%250===0)f.deadline=d;
 return f;
}
export function writeFilters(f:Filters){const p=new URLSearchParams();if(f.query)p.set('q',f.query);if(f.selected.length)p.set('systems',f.selected.join(','));for(const key of ['suite','dataset','hardware','policy','sensor','evidence','budget','duration','deadline'] as const)if(f[key]!==defaults[key])p.set(key,String(f[key]));return p.toString();}
export function csv(rows:Row[],deadline:number){
 const cell=(v:unknown)=>'"'+String(typeof v==='string'&&/^[=+@\-]/.test(v)?"'"+v:v??'unknown').replaceAll('"','""')+'"';
 const headers=['Evidence','Configuration','Task','Session','Suite','Quality','Success at selected deadline','Deadline ms','Latency ms (failure penalized)','Critical facts correct','Critical facts total','Cost USD','Status','Trace SHA256'];
 return [headers,...rows.map(r=>[r.evidence,r.system_id,r.task_id,r.session_id,r.suite,r.quality,Number(r.quality>0&&r.latency_ms<=deadline),deadline,r.latency_ms,r.correct_facts,r.critical_facts,r.cost_usd,r.status,r.trace_sha256])].map(row=>row.map(cell).join(',')).join('\r\n');
}
