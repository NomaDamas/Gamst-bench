import BenchmarkAtlas from './BenchmarkAtlas';
import catalog from '../data/catalog.json';
import {useEffect,useState} from 'react';
import type {ReactNode} from 'react';
import {ArrowDownToLine,ArrowRight,ArrowUpRight,BarChart3,Check,Github,Link2,MousePointer2,RotateCcw,Search,ShieldCheck,SlidersHorizontal,X} from 'lucide-react';
import {data,primary,defaults,suites,colors,filterRows,summarize,pareto,readFilters,writeFilters,csv,inDuration} from './benchmark';
import type {Filters,Row,Summary,System} from './benchmark';

const repo='https://github.com/NomaDamas/Gamst-bench';
const pct=(v:number|null)=>v===null?'—':(v*100).toFixed(1)+'%';
const num=(v:number|null,d=0)=>v===null?'—':v.toFixed(d);
const synthetic=data.evidence==='synthetic';

export const pages=[
 {id:'overview',label:'Overview'},
 {id:'results',label:'Results'},
 {id:'benchmarks',label:'Benchmarks'},
 {id:'method',label:'Method'},
] as const;
type Page=typeof pages[number]['id'];
const readPage=():Page=>pages.find(p=>'#'+p.id===location.hash)?.id??'overview';

/** Catalog arm describing each matched configuration's pipeline. */
const armFor:Record<string,string>={A:'baseline',B:'gamst-llm',C:'gamst-vlm',D:'periodic',E:'streaming'};

function download(value:string,name:string,type:string){const url=URL.createObjectURL(new Blob([value],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function Title({title,sub,extra}:{title:string;sub:string;extra?:ReactNode}){return <div className="panel-title"><div><h2>{title}</h2><p>{sub}</p></div>{extra}</div>;}
function Empty(){return <div className="empty"><Search size={24}/><strong>No matching evidence</strong><span>Change the filters or reset the view.</span></div>;}
function ChartButton({label,onClick,children}:{label:string;onClick:()=>void;children:ReactNode}){return <g role="button" tabIndex={0} aria-label={label} onClick={onClick} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onClick();}}} className="chart-target">{children}</g>;}
function EvidenceBanner(){return <div className="evidence-banner"><ShieldCheck size={17}/><p><strong>{synthetic?'Synthetic protocol fixtures — not model performance.':'Measured evidence, with provenance.'}</strong> {data.provenance} {synthetic&&'Numbers show how results will read once GCP runs land; they cannot establish savings.'}</p><a href={repo+'/tree/main/fixtures'}>Artifacts <ArrowUpRight size={13}/></a></div>;}

export default function App(){
 const [page,setPage]=useState<Page>(readPage);
 const [f,setF]=useState<Filters>(()=>readFilters(location.search));
 const [notice,setNotice]=useState('');
 const [view,setView]=useState<'ranking'|'diagnostics'|'traces'>('ranking');
 const [taskId,setTask]=useState('');
 const [resource,setResource]=useState<'rss_mb'|'age_ms'|'dropped'>('rss_mb');
 const [sort,setSort]=useState<'success'|'costHour'|'p95'|'critical'>('success');
 useEffect(()=>{const query=writeFilters(f);history.replaceState(null,'',location.pathname+(query?'?'+query:'')+location.hash);},[f]);
 useEffect(()=>{const fn=()=>{setF(readFilters(location.search));setPage(readPage());};addEventListener('popstate',fn);addEventListener('hashchange',fn);return()=>{removeEventListener('popstate',fn);removeEventListener('hashchange',fn);};},[]);
 useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),3500);return()=>clearTimeout(timer);},[notice]);
 const go=(p:Page)=>{if(p!==page)history.pushState(null,'',location.pathname+location.search+'#'+p);setPage(p);};
 const update=(p:Partial<Filters>)=>setF(v=>({...v,...p}));
 const select=(id:string)=>setF(v=>({...v,selected:v.selected.includes(id)?v.selected.filter(s=>s!==id):[...v.selected,id]}));
 const focus=(id:string)=>{setF(v=>({...v,selected:[id]}));go('results');};

 const rows=filterRows(f);
 const visible=primary.map(s=>({...s,metrics:summarize(rows.filter(r=>r.system_id===s.id),f.deadline)})).filter(s=>s.metrics.n);
 const summary=summarize(rows,f.deadline);
 const changed=writeFilters(f)!=='';

 return <><a href="#main" className="skip-link">Skip to content</a>
  <header className="header"><div className="header-inner"><a className="brand" href="#overview" onClick={e=>{e.preventDefault();go('overview');}}><span className="brand-icon"><BarChart3 size={22}/></span>GAMST<span className="brand-light">Bench</span></a>
   <nav aria-label="Sections" role="tablist">{pages.map(p=><a key={p.id} href={'#'+p.id} role="tab" aria-selected={page===p.id} className={page===p.id?'nav-active':''} onClick={e=>{e.preventDefault();go(p.id);}}>{p.label}</a>)}</nav>
   <a className="github-link" href={repo} target="_blank" rel="noreferrer"><Github size={17}/>GitHub<ArrowUpRight size={14}/></a></div></header>
  <main id="main">
   {page==='overview'&&<Overview rows={data.rows} deadline={f.deadline} focus={focus} go={go}/>}
   {page==='results'&&<section className="results">
    <div className="section-top"><div><span className="eyebrow muted">MATCHED CONFIGURATIONS</span><h2>Results</h2></div><div className="actions"><button className="button" onClick={async()=>{try{await navigator.clipboard.writeText(location.href);setNotice('Filtered view link copied');}catch{setNotice('Copy the address bar URL to share this view.');}}}><Link2 size={15}/>Share view</button><button className="button" onClick={()=>download(csv(rows,f.deadline),'gamst-context-'+data.evidence+'.csv','text/csv;charset=utf-8')} disabled={!rows.length}><ArrowDownToLine size={15}/>Export</button></div></div>
    <Toolbar f={f} update={update} changed={changed} reset={()=>setF({...defaults})}/>
    <div className="selection-line"><div className="selection-info"><MousePointer2 size={14}/><span>Click any chart element to filter everything.</span>{f.selected.map(id=><button className="selection-chip" key={id} onClick={()=>select(id)}>{primary.find(s=>s.id===id)?.name}<X size={12}/></button>)}{f.duration!=='all'&&<button className="selection-chip" onClick={()=>update({duration:'all'})}>{f.duration} events<X size={12}/></button>}</div><span className="count" aria-live="polite">{visible.length} configurations · {rows.length} task runs</span></div>
    <div className="stats">
     <Stat label="GROUNDED & ON TIME" value={pct(summary.success)} foot={`${f.deadline}ms deadline`}/>
     <Stat label="CRITICAL FACT RECALL" value={pct(summary.critical)} foot="Required facts preserved"/>
     <Stat label="ANSWER LATENCY P95" value={num(summary.p95)} unit="ms" foot="Timeouts penalized"/>
     <Stat label="WHOLE-PIPELINE COST" value={summary.costHour===null?'—':'$'+summary.costHour.toFixed(2)} unit="/ stream h" foot={synthetic?'Illustrative accounting':'Unknown charges stay unknown'}/>
    </div>
    <div className="subtabs" role="group" aria-label="Result view">{([['ranking','Ranking'],['diagnostics','Diagnostics'],['traces','Traces']] as const).map(([id,label])=><button key={id} aria-pressed={view===id} onClick={()=>setView(id)}>{label}</button>)}</div>
    {view==='ranking'&&<Ranking rows={rows} visible={visible} f={f} update={update} select={select} sort={sort} setSort={setSort}/>}
    {view==='diagnostics'&&<Diagnostics rows={rows} visible={visible} summary={summary} f={f} update={update} select={select}/>}
    {view==='traces'&&<Traces rows={rows} taskId={taskId} setTask={setTask} resource={resource} setResource={setResource} select={select}/>}
   </section>}
   {page==='benchmarks'&&<BenchmarkAtlas/>}
   {page==='method'&&<Method/>}
  </main>
  <footer className="footer"><span className="brand"><span className="brand-icon small"><BarChart3 size={16}/></span>GAMST Bench</span><span>Real-time perception for LLMs, at a fraction of VLM cost.</span><div><a href={repo+'/blob/main/README.md'}>Results & source ↗</a><span>{data.protocol}</span></div></footer>
  {notice&&<div className="toast" role="status"><Check size={17}/>{notice}</div>}</>;
}

type Visible=(System&{metrics:Summary})[];

function Stat({label,value,unit,foot}:{label:string;value:string;unit?:string;foot:string}){return <div className="stat"><span className="stat-label">{label}</span><div className="stat-value">{value}{unit&&<span>{unit}</span>}</div><span className="stat-foot">{foot}</span></div>;}

const change=(ratio:number)=>(ratio<=1?'−':'+')+(Math.abs(1-ratio)*100).toFixed(0)+'%';

function Overview({rows,deadline,focus,go}:{rows:Row[];deadline:number;focus:(id:string)=>void;go:(p:Page)=>void}){
 const [against,setAgainst]=useState(data.comparisons[0]?.baseline??'');
 const systems=primary.map(s=>({...s,metrics:summarize(rows.filter(r=>r.system_id===s.id),deadline)}));
 const main=data.comparisons.find(c=>c.baseline===against);
 const baseline=primary.find(s=>s.id===against)?.name??against;
 const verdict=main?[
  {label:'Whole-pipeline cost',value:main.point.cost_ratio,show:change,gate:'gate ≤ 0.80×',pass:main.gates.cost},
  {label:'Answer latency p95',value:main.point.latency_ratio,show:change,gate:'gate ≤ 0.90×',pass:main.gates.latency},
  {label:'Grounded quality',value:main.point.quality_delta,show:(v:number)=>(v>=0?'+':'')+(v*100).toFixed(1)+' pt',gate:'gate ≥ 0',pass:main.gates.quality},
 ]:[];
 return <>
  <section className="hero"><div className="eyebrow"><span className="status-dot"/> PERCEPTION LAYER FOR EXISTING LLMS</div>
   <h1>See in real time.<br/><span>Stop paying a VLM per frame.</span></h1>
   <p className="hero-copy">Gamst gives an existing LLM eyes and ears: lightweight perception runs continuously, a VLM is called only when meaning changes. This benchmark checks that the LLM still gets grounded, on-time context at a fraction of the cost.</p>
   <div className="hero-links"><button className="button primary" onClick={()=>go('results')}>See results <ArrowRight size={16}/></button><button className="text-link" onClick={()=>go('benchmarks')}>Which benchmarks test this?</button></div></section>
  <EvidenceBanner/>
  {main&&<section className="verdict" aria-label="Headline comparison"><div className="verdict-top"><span className="eyebrow muted">GAMST HYBRID vs {baseline.toUpperCase()} · SAME CONSUMER LLM</span><div className="subtabs compact" role="group" aria-label="Compare against">{data.comparisons.map(c=><button key={c.baseline} aria-pressed={c.baseline===against} onClick={()=>setAgainst(c.baseline)}>vs {primary.find(s=>s.id===c.baseline)?.name??c.baseline}</button>)}</div></div>
   <div className="verdict-grid">{verdict.map(v=><div key={v.label} className={'verdict-card'+(v.pass?'':' fails')}><span>{v.label}</span><strong>{v.value===null||v.value===undefined?'—':v.show(v.value)}</strong><small>{v.gate} · {v.pass?'meets':'misses'}</small></div>)}</div>
   <p className="verdict-note">{main.status==='not_passed'?'Acceptance not passed':'Numeric pass · audit required'} — {synthetic?'synthetic data cannot pass the measured / held-out gates.':'see Method for every gate and 95% CI.'}</p></section>}
  <div className="chart-grid"><section className="panel"><Title title="Cost vs grounded success" sub="Top-left wins. Click a pipeline to open its results." extra={<span className="mini-badge">{deadline}ms deadline</span>}/><Frontier systems={systems} select={focus}/></section>
   <section className="panel"><Title title="Same quality, fewer VLM calls" sub="Grounded success as the VLM call budget grows. Selective (Gamst) vs fixed schedule, same VLM."/><BudgetCurve deadline={deadline}/></section></div>
  <section className="arms" aria-label="Pipelines compared">{systems.map(s=>{const arm=catalog.arms.find(a=>a.id===armFor[s.id]);return <button key={s.id} className="arm-card" onClick={()=>focus(s.id)}><span className="arm-head"><i style={{background:colors[s.id]}}/>{s.id} · {s.name}</span><span className="arm-path">{arm?.path.join(' → ')}</span><span className="arm-metrics"><strong>{pct(s.metrics.success)}</strong> on time · <strong>{s.metrics.costHour===null?'—':'$'+s.metrics.costHour.toFixed(2)}</strong>/h</span></button>;})}</section>
 </>;
}

function BudgetCurve({deadline}:{deadline:number}){
 const series=[{policy:'hybrid',label:'Gamst selective',color:colors.C},{policy:'periodic',label:'Periodic',color:colors.D}].map(line=>({...line,points:data.systems.filter(s=>s.policy===line.policy).map(s=>({id:s.id,calls:s.budget_calls,success:summarize(data.rows.filter(r=>r.system_id===s.id),deadline).success})).sort((a,b)=>a.calls-b.calls)}));
 const budgets=[...new Set(series.flatMap(s=>s.points.map(p=>p.calls)))].sort((a,b)=>a-b);
 if(budgets.length<2)return <Empty/>;
 // Log-spaced budgets: place each distinct budget at an even step so 1…12 calls stay readable.
 const x=(calls:number)=>55+budgets.indexOf(calls)/(budgets.length-1)*495;
 const reference=primary.find(s=>s.policy==='vlm');
 const refSuccess=reference?summarize(data.rows.filter(r=>r.system_id===reference.id),deadline).success:null;
 return <><svg className="scatter" viewBox="0 0 590 300" role="group" aria-label="VLM budget curve">{[0,25,50,75,100].map(t=><g key={t}><line className="grid-line" x1="55" x2="550" y1={250-t*2.1} y2={250-t*2.1}/><text x="42" y={254-t*2.1} textAnchor="end">{t}%</text></g>)}{budgets.map(b=><text key={b} x={x(b)} y="271" textAnchor="middle">{b}</text>)}<text className="axis-label" x="55" y="18">GROUNDED, ON-TIME SUCCESS ↑</text><text className="axis-label" x="300" y="295" textAnchor="middle">VLM CALLS PER 30 s SESSION →</text>
  {refSuccess!==null&&<g><line x1="55" x2="550" y1={250-refSuccess*210} y2={250-refSuccess*210} stroke={colors[reference!.id]} strokeDasharray="5 4"/><text className="point-label" x="548" y={244-refSuccess*210} textAnchor="end">{reference!.name} · {reference!.budget_calls} calls</text></g>}
  {series.map(s=><g key={s.policy}><polyline points={s.points.map(p=>`${x(p.calls)},${250-(p.success??0)*210}`).join(' ')} fill="none" stroke={s.color} strokeWidth="2.5"/>{s.points.map(p=><circle key={p.id} cx={x(p.calls)} cy={250-(p.success??0)*210} r="4" fill={s.color}><title>{s.label} · {p.calls} calls: {pct(p.success)}</title></circle>)}</g>)}</svg>
  <div className="chart-footer legend">{series.map(s=><span key={s.policy}><i style={{background:s.color}}/>{s.label}</span>)}<span>Dashed: VLM-centered reference</span></div></>;
}

function Frontier({systems,select}:{systems:Visible;select:(id:string)=>void}){
 const shown=systems.filter(s=>s.metrics.n);
 if(!shown.length)return <Empty/>;
 const costMax=Math.max(1,Math.ceil(Math.max(0,...shown.map(s=>s.metrics.costHour??0))*1.2));
 const frontier=pareto(shown.map(s=>({id:s.id,cost:s.metrics.costHour,success:s.metrics.success})));
 return <><svg className="scatter" viewBox="0 0 590 300" aria-label="Cost and success chart" role="group">{[0,25,50,75,100].map(t=><g key={t}><line className="grid-line" x1="55" x2="550" y1={250-t*2.1} y2={250-t*2.1}/><text x="42" y={254-t*2.1} textAnchor="end">{t}%</text></g>)}{[0,1,2,3,4].map(t=><text key={t} x={55+t*123.75} y="271" textAnchor="middle">${(t*costMax/4).toFixed(1)}</text>)}<text className="axis-label" x="55" y="18">GROUNDED, ON-TIME SUCCESS ↑</text><text className="axis-label" x="300" y="295" textAnchor="middle">TOTAL USD / STREAM HOUR →</text>
  {shown.map(s=>s.metrics.costHour===null||s.metrics.success===null?null:<ChartButton key={s.id} label={'Filter by '+s.name} onClick={()=>select(s.id)}><title>{s.name}: {pct(s.metrics.success)}, ${s.metrics.costHour.toFixed(2)}/h</title><circle cx={55+s.metrics.costHour/costMax*495} cy={250-s.metrics.success*210} r="16" fill="transparent"/><circle cx={55+s.metrics.costHour/costMax*495} cy={250-s.metrics.success*210} r="8" fill={colors[s.id]??'#888'} stroke={frontier.includes(s.id)?'#3d3053':'white'} strokeWidth="2"/><text className="point-label" x={55+s.metrics.costHour/costMax*495+12} y={242-s.metrics.success*210}>{s.id} · {s.name}</text></ChartButton>)}</svg>
  <div className="chart-footer"><span>Outlined: Pareto-efficient</span><span>Unknown cost is not plotted</span></div></>;
}

function Toolbar({f,update,changed,reset}:{f:Filters;update:(p:Partial<Filters>)=>void;changed:boolean;reset:()=>void}){
 const dropdown=(label:string,key:'dataset'|'hardware'|'policy'|'sensor'|'evidence'|'budget',options:string[])=><label className="select-field"><span>{label}</span><select aria-label={label} value={f[key]} onChange={e=>update({[key]:e.target.value})}><option value="all">All</option>{options.map(v=><option key={v} value={v}>{key==='budget'?'≤ $'+v+'/h':v}</option>)}</select></label>;
 const advanced=(['query','hardware','policy','evidence','dataset','sensor','budget'] as const).filter(k=>f[k]!==defaults[k]).length;
 return <div className="toolbar">
  <div className="toolbar-row"><div className="category-tabs" role="group" aria-label="Suite"><button aria-pressed={f.suite==='all'} onClick={()=>update({suite:'all'})}>All suites</button>{Object.entries(suites).map(([id,s])=><button key={id} aria-pressed={f.suite===id} onClick={()=>update({suite:id})} title={s.description}>{s.short}</button>)}</div>
   <label className="deadline-control"><span>Deadline <strong>{(f.deadline/1000).toFixed(2)}s</strong></span><input aria-label="Response deadline" type="range" min="250" max="10000" step="250" value={f.deadline} onChange={e=>update({deadline:Number(e.target.value)})}/></label>
   <button className="reset" disabled={!changed} onClick={reset}><RotateCcw size={14}/>Reset</button></div>
  <details className="more-filters"><summary><SlidersHorizontal size={14}/>More filters{advanced?` · ${advanced} active`:''}</summary><div className="filter-bar"><label className="search"><Search size={16}/><input aria-label="Search configurations" placeholder="Search configurations…" value={f.query} onChange={e=>update({query:e.target.value})}/></label>{dropdown('Hardware','hardware',[...new Set(primary.map(s=>s.hardware))])}{dropdown('Policy','policy',[...new Set(primary.map(s=>s.policy))])}{dropdown('Evidence','evidence',['measured','synthetic'])}{dropdown('Dataset','dataset',[...new Set(data.rows.map(r=>r.dataset))])}{dropdown('Sensors','sensor',[...new Set(data.rows.map(r=>r.sensor_track))])}{dropdown('Budget','budget',['0.5','1','2','4'])}</div></details>
 </div>;
}

function Ranking({rows,visible,f,update,select,sort,setSort}:{rows:Row[];visible:Visible;f:Filters;update:(p:Partial<Filters>)=>void;select:(id:string)=>void;sort:'success'|'costHour'|'p95'|'critical';setSort:(s:'success'|'costHour'|'p95'|'critical')=>void}){
 const ordered=[...visible].sort((a,b)=>{const av=a.metrics[sort],bv=b.metrics[sort];if(av===null)return 1;if(bv===null)return -1;return sort==='costHour'||sort==='p95'?av-bv:bv-av;});
 return <>
  <section className="panel leaderboard"><Title title="Leaderboard" sub="Each row is a full pipeline: perception, VLM policy, consumer LLM and hardware." extra={<span className="mini-badge">{data.evidence.toUpperCase()}</span>}/><div className="table-scroll"><table><caption className="sr-only">Pipeline configurations</caption><thead><tr><th>ID</th><th>Configuration</th><th className="score-column"><button onClick={()=>setSort('success')}>On-time success</button></th><th><button onClick={()=>setSort('critical')}>Critical recall</button></th><th><button onClick={()=>setSort('p95')}>Answer p95</button></th><th><button onClick={()=>setSort('costHour')}>Total $ / h</button></th><th>Failures</th></tr></thead><tbody>{ordered.map(s=><tr key={s.id}><td>{s.id}</td><th><label className="model-cell"><input type="checkbox" aria-label={'Compare '+s.name} checked={f.selected.includes(s.id)} onChange={()=>select(s.id)}/><span><strong>{s.name}</strong><small><i style={{background:colors[s.id]}}/>{s.policy} · {s.model}</small></span></label></th><td className="score-column"><strong>{pct(s.metrics.success)}</strong></td><td>{pct(s.metrics.critical)}</td><td>{num(s.metrics.p95)}ms</td><td>{s.metrics.costHour===null?'Unknown':'$'+s.metrics.costHour.toFixed(2)}</td><td>{s.metrics.failures} / {s.metrics.n}</td></tr>)}</tbody></table>{!visible.length&&<Empty/>}</div><div className="table-footer"><span>Consumer: {data.consumer} · {data.hardware}</span><span>Context p95, peak memory and traces: Diagnostics / Traces</span></div></section>
  <section className="panel dimensions"><Title title="By suite" sub="Grounded, on-time success per Gamst suite. Click to filter."/><div className="dimension-grid">{Object.keys(suites).map(id=>{const m=summarize(rows.filter(r=>r.suite===id),f.deadline);return <button key={id} className="dimension" aria-label={'Filter suite '+suites[id].short} aria-pressed={f.suite===id} onClick={()=>update({suite:f.suite===id?'all':id})}><span>{suites[id].short}</span><strong>{pct(m.success)}</strong><div className="dimension-track"><span style={{width:(m.success??0)*100+'%'}}/></div><small>{m.n} task runs</small></button>;})}</div></section>
 </>;
}

function Diagnostics({rows,visible,summary,f,update,select}:{rows:Row[];visible:Visible;summary:Summary;f:Filters;update:(p:Partial<Filters>)=>void;select:(id:string)=>void}){
 return <>
  <section className="panel"><Title title="Success vs allowed latency" sub="How each pipeline's grounded success grows as the deadline loosens."/>{visible.length?<svg className="scatter wide" viewBox="0 0 590 300" role="group" aria-label="Success deadline curves">{[0,50,100].map(t=><g key={t}><line className="grid-line" x1="55" x2="550" y1={250-t*2.1} y2={250-t*2.1}/><text x="42" y={254-t*2.1} textAnchor="end">{t}%</text></g>)}{[0,2,4,6,8,10].map(t=><text key={t} x={55+t/10*495} y="272" textAnchor="middle">{t}s</text>)}<text className="axis-label" x="55" y="18">GROUNDED SUCCESS ↑</text><line x1={55+f.deadline/10000*495} x2={55+f.deadline/10000*495} y1="35" y2="250" stroke="#d2c6e8" strokeDasharray="4 4"/>{visible.map(s=>{const list=rows.filter(r=>r.system_id===s.id);const points=Array.from({length:41},(_,i)=>`${55+i/40*495},${250-(summarize(list,i*250).success??0)*210}`).join(' ');return <ChartButton key={s.id} label={'Select '+s.name+' curve'} onClick={()=>select(s.id)}><polyline points={points} fill="none" stroke="transparent" strokeWidth="16"/><polyline points={points} fill="none" stroke={colors[s.id]} strokeWidth="2.5"/></ChartButton>;})}<text className="axis-label" x="300" y="295" textAnchor="middle">ALLOWED RESPONSE LATENCY →</text></svg>:<Empty/>}<div className="chart-footer legend">{primary.map(s=><button key={s.id} aria-pressed={f.selected.includes(s.id)} onClick={()=>select(s.id)}><i style={{background:colors[s.id]}}/>{s.id} · {s.name}</button>)}</div></section>
  <div className="diagnostic-grid"><section className="panel"><Title title="Missed brief events" sub="Critical-fact miss rate by evidence duration. Click to filter."/><div className="duration-bars">{[['short','≤ 500ms'],['medium','0.5–2s'],['long','> 2s']].map(([id,label])=>{const m=summarize(rows.filter(r=>inDuration(r,id)),f.deadline);return <button key={id} aria-label={'Filter '+id+' events'} aria-pressed={f.duration===id} onClick={()=>update({duration:f.duration===id?'all':id})}><span>{label}</span><div className="bar-track"><span style={{width:(m.critical===null?0:1-m.critical)*100+'%'}}/></div><strong>{m.critical===null?'—':pct(1-m.critical)}</strong></button>;})}</div></section>
   <section className="panel"><Title title="Honesty" sub="Silence and repetition earn no free points."/><div className="honesty-grid"><div><strong>{pct(summary.unsupported)}</strong><span>Unsupported claims</span></div><div><strong>{pct(summary.stale)}</strong><span>Stale-state errors</span></div><div><strong>{pct(summary.abstain)}</strong><span>Abstentions</span></div><div><strong>{num(summary.falseAlerts,1)}</strong><span>False alerts / h</span></div></div></section></div>
 </>;
}

function Traces({rows,taskId,setTask,resource,setResource,select}:{rows:Row[];taskId:string;setTask:(id:string)=>void;resource:'rss_mb'|'age_ms'|'dropped';setResource:(r:'rss_mb'|'age_ms'|'dropped')=>void;select:(id:string)=>void}){
 const tasks=[...new Set(rows.map(r=>r.task_id))];const activeTask=tasks.includes(taskId)?taskId:tasks[0];const taskRows=rows.filter(r=>r.task_id===activeTask);const maxTimeline=Math.max(1000,...taskRows.flatMap(r=>r.timeline.map(e=>e.received_ms)));
 return <>
  <section className="panel trace-panel"><Title title="Follow the evidence" sub="Evidence, context delivery and answer on one clock." extra={<select aria-label="Inspect task" value={activeTask??''} onChange={e=>setTask(e.target.value)}>{tasks.map(id=><option key={id}>{id}</option>)}</select>}/>{taskRows.length?<div className="timeline-wrap">{taskRows.map(r=><div className="timeline-row" key={r.system_id}><button onClick={()=>select(r.system_id)} aria-label={'Select timeline '+r.system_id}>{r.system_id}<i style={{background:colors[r.system_id]}}/></button><div className="timeline-track">{r.timeline.map((e,i)=><span key={i} style={{left:Math.min(96,e.received_ms/maxTimeline*94)+'%'}} className={'timeline-event event-'+e.type} title={`${e.type} · ${(e.received_ms/1000).toFixed(2)}s · ${e.label}`}><i/><small>{e.type}</small></span>)}</div><span>{r.quality?'Grounded':'Incorrect'} · {r.latency_ms}ms</span></div>)}<div className="trace-details">{taskRows.map(r=><details key={r.system_id}><summary>{r.system_id} · {r.task_id} · inspect trace</summary>{r.timeline.map((e,i)=><p key={i}><code>{(e.received_ms/1000).toFixed(2)}s · {e.type}</code> {e.label}</p>)}<p>Trace SHA256: <code>{r.trace_sha256}</code></p></details>)}</div></div>:<Empty/>}</section>
  <section className="panel resource-panel"><Title title="Resources over time" sub={synthetic?'30-second synthetic traces are not a 2h / 8h soak.':'Check duration and scope before sustained-operation claims.'} extra={<select aria-label="Resource metric" value={resource} onChange={e=>setResource(e.target.value as typeof resource)}><option value="rss_mb">Resident memory (MB)</option><option value="age_ms">Observation age (ms)</option><option value="dropped">Dropped inputs</option></select>}/>{taskRows.length?<ResourceChart rows={taskRows} metric={resource} select={select}/>:<Empty/>}<div className="chart-footer"><span>Unknown measurements are gaps, never zero.</span></div></section>
 </>;
}

function Method(){
 return <>
  <section className="methodology"><div><span className="eyebrow muted">HOW A RESULT COUNTS</span><h2>Same inputs, same consumer LLM.<br/>Only the perception pipeline changes.</h2><p>Streams replay in real time, slow inference never pauses them, and failures stay in the denominator.</p><a className="text-link" href={repo+'/blob/main/docs/PROTOCOL.md'}>Full evaluation protocol <ArrowUpRight size={14}/></a></div>
   <div className="method-cards">
    <article><span>01</span><div><h3>Grounded, correct, on time</h3><p>A task succeeds only with a correct answer, a supporting observation and the predeclared deadline.</p></div></article>
    <article><span>02</span><div><h3>Every cost counted</h3><p>VLM charges, lightweight models, ASR, consumer LLM and retries, per stream hour. Local is not free.</p></div></article>
    <article><span>03</span><div><h3>Official scores stay official</h3><p>Published benchmarks keep their own protocol and scorer; Gamst extensions are reported as a separate track.</p></div></article>
   </div></section>
  <section className="panel acceptance"><Title title="Acceptance gates" sub="Preregistered; independent of any filter. Session-paired 95% bootstrap intervals."/>{data.comparisons.map(c=><div className="gate-row" key={c.baseline}><strong>{c.candidate} vs {c.baseline}</strong>{[['cost_ratio','Cost ratio','≤ 0.80'],['latency_ratio','p95 ratio','≤ 0.90'],['quality_delta','Quality difference','≥ 0']].map(([key,label,threshold])=><div key={key}><span>{label} · {threshold}</span><strong>{num(c.point[key]??null,3)}</strong><small>95% CI {c.ci95[key]?.map(n=>n.toFixed(3)).join(' – ')??'unknown'}</small></div>)}<span className="gate-status">{c.status==='not_passed'?'Not passed':'Numeric pass · audit required'}</span><details><summary>All checks</summary>{Object.entries(c.gates).map(([key,passed])=><p key={key}>{passed?'✓':'×'} {key}</p>)}<p>{c.clusters} independent session clusters</p></details></div>)}<p className="acceptance-note">Synthetic evidence cannot pass. Missing cost, missing pairs, unresolved critical facts and inconclusive quality are not passes.</p></section>
  <section className="panel official"><Title title="Official-protocol runs" sub="Our reproductions of external benchmarks under their own scorers."/>{data.official_scores.length?<div className="official-items">{data.official_scores.map((s,i)=><a key={i} href={s.source_url}>{s.benchmark} · {s.system_id}: {s.score}/{s.scale} · {s.metric} · {s.split} · {s.evaluation_mode} · {s.protocol_revision}</a>)}</div>:<div className="official-items">{catalog.benchmarks.filter(b=>b.phase===1).map(b=><div key={b.id}><strong>{b.name}</strong><span>Not measured</span></div>)}</div>}</section>
  <section className="panel"><Title title="Readiness" sub={`${catalog.readiness.runtime} · ${catalog.readiness.status.replace('_',' ')}`}/><ol className="readiness">{catalog.readiness.requirements.map(r=><li key={r}>{r}</li>)}</ol><div className="chart-footer"><a href={repo+'/blob/main/docs/RUNBOOK.md'}>Runbook ↗</a><a href={repo+'/blob/main/docs/MCP.md'}>Multi-benchmark MCP ↗</a></div></section>
 </>;
}

function ResourceChart({rows,metric,select}:{rows:Row[];metric:'rss_mb'|'age_ms'|'dropped';select:(id:string)=>void}){
 const maxX=Math.max(1,...rows.flatMap(r=>r.resources.map(p=>p.at_ms)));const maxY=Math.max(1,...rows.flatMap(r=>r.resources.map(p=>p[metric]??0)))*1.1;
 return <svg className="resource-chart" viewBox="0 0 1000 240" role="group" aria-label="Resource history">{[0,.5,1].map(t=><g key={t}><line x1="60" x2="960" y1={190-t*155} y2={190-t*155} className="grid-line"/><text x="48" y={194-t*155} textAnchor="end">{(t*maxY).toFixed(0)}</text></g>)}{[0,.25,.5,.75,1].map(t=><text key={t} x={60+t*900} y="220" textAnchor="middle">{(t*maxX/1000).toFixed(0)}s</text>)}{rows.map(r=>{let path='';let gap=true;for(const p of r.resources){if(p[metric]===null){gap=true;continue;}path+=(gap?'M':'L')+(60+p.at_ms/maxX*900)+','+(190-p[metric]!/maxY*155)+' ';gap=false;}return <ChartButton key={r.system_id} label={'Select resource '+r.system_id} onClick={()=>select(r.system_id)}><path d={path} stroke="transparent" strokeWidth="16" fill="none"/><path d={path} stroke={colors[r.system_id]} strokeWidth="2.5" fill="none"/></ChartButton>;})}</svg>;
}
