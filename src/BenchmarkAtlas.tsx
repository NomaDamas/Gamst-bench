import {useState} from 'react';
import catalog from '../data/catalog.json';
import recipes from '../mcp/recipes.json';
import {data,suites} from './benchmark';
import type {Report} from './benchmark';

const atlasBenchmarks=catalog.benchmarks as Array<Record<string, any>>;
export const problems:{id:string;short:string;description:string}[]=[
 ...Object.entries(suites).map(([id,s])=>({id,short:s.short,description:s.description})),
 {id:'timing',short:'Timing',description:'Respond when it matters, stay silent otherwise.'},
 {id:'cost',short:'Cost / latency',description:'Wall-clock latency and whole-pipeline compute cost.'},
];
type Coverage=Record<string,string|undefined>;

export default function BenchmarkAtlas({report=data}:{report?:Pick<Report,'evidence'|'official_scores'>}={}){
 const [index,setIndex]=useState(0),[view,setView]=useState<'published'|'gamst'>('published');
 const b=atlasBenchmarks[index];
 const covers=b.covers as Coverage;
 const measured=report.evidence==='measured'?report.official_scores.filter(r=>r.benchmark===b.name):[];
 const gaps=problems.filter(p=>!atlasBenchmarks.some(x=>(x.covers as Coverage)[p.id]==='direct'));
 const selectBenchmark=(i:number)=>{setIndex(i);setView('published');};
 return <section id="benchmarks" className="atlas">
  <div className="section-top"><div><span className="eyebrow muted">BENCHMARK ATLAS · REVIEWED {catalog.reviewed_at}</span><h2>External benchmarks and Gamst evaluation</h2><p className="section-sub">Representative tracks, supporting regressions and the Gamst self-evaluation are kept separate. ● direct · ○ partial · ⏳ to be continued.</p></div></div>
  <div className="atlas-index" aria-label="Benchmark index">{atlasBenchmarks.map((x,i)=><button key={x.id} aria-label={'Open '+x.name+' index'} aria-pressed={i===index} onClick={()=>selectBenchmark(i)}><span>{x.emoji??'▫️'}</span><strong>{x.name}</strong><small>{x.index_line??x.problem}</small><em>{x.status_detail??x.integration}</em></button>)}</div>
  <div className="panel table-scroll"><table className="coverage" aria-label="Benchmark coverage"><thead><tr><th>Benchmark</th>{problems.map(p=><th key={p.id} title={p.description}>{p.short}</th>)}<th>Best published</th></tr></thead>
   <tbody>{atlasBenchmarks.map((x,i)=>{const c=x.covers as Coverage;const top=[...x.results].sort((p:any,q:any)=>q.value-p.value)[0];return <tr key={x.id} className={i===index?'selected-row':''}><th><button aria-label={x.name} aria-pressed={i===index} aria-controls="atlas-detail" onClick={()=>selectBenchmark(i)}><strong>{x.emoji??'▫️'} {x.name}</strong><small>{x.venue} · {x.status_detail??x.integration}</small></button></th>{problems.map(p=><td key={p.id} className={'cov cov-'+(c[p.id]??'none')} aria-label={c[p.id]?p.short+': '+c[p.id]:undefined}>{c[p.id]==='direct'?'●':c[p.id]==='partial'?'○':''}</td>)}<td className="best">{top?<><strong>{top.value}{top.unit}</strong><small>{top.model}</small></>:<small>—</small>}</td></tr>;})}</tbody>
   <tfoot><tr><th>Gap Gamst Bench fills</th>{problems.map(p=><td key={p.id} className="cov">{gaps.includes(p)?'★':''}</td>)}<td><small>★ no primary benchmark</small></td></tr></tfoot></table></div>
  <div id="atlas-detail" role="region" aria-label={b.name+' details'} className="panel atlas-detail"><div className="atlas-heading"><h3>{b.emoji??'▫️'} {b.name}</h3><span>{b.venue} · Phase {b.phase} · ⏳ {b.status_detail??b.integration}</span><a href={b.source_url} target="_blank" rel="noreferrer">Official source ↗</a></div>
   <div className="atlas-grid"><article><span className="eyebrow muted">WHAT IT ASKS</span><h4>{b.question_focus??b.problem}</h4><p>{b.abilities??b.existing}</p><p><strong>Data:</strong> {b.data_shape??b.dataset_size}</p><p className="chips">{problems.filter(p=>covers[p.id]).map(p=><span key={p.id} className={'chip chip-'+covers[p.id]}>{p.short}</span>)}</p></article><article><span className="eyebrow muted">GAMST HYPOTHESIS · TO BE CONTINUED</span><h4>What the hybrid must prove</h4><p>{b.gamst}</p><p><strong>Measure:</strong> {b.metric}</p><p><strong>Model setup:</strong> {b.model_setup??'Pin checkpoint, precision, prompt, hardware and scorer before running.'}</p></article></div>
   <div className="atlas-views" role="group" aria-label="Result evidence"><button aria-pressed={view==='published'} onClick={()=>setView('published')}>Published references</button><button aria-pressed={view==='gamst'} onClick={()=>setView('gamst')}>Our GCP runs</button></div>
   {view==='published'?<div className="reference-grid">{b.results.length?b.results.map((r:any,i:number)=><article key={i} className="reference-card"><span className="mini-badge">PUBLISHED · NOT REPRODUCED</span><h4>{r.model}</h4><strong className="reference-value">{r.value}{r.unit}</strong><p>{r.metric}</p><small>{r.scope}</small><a href={r.source_url} target="_blank" rel="noreferrer">Result source ↗</a></article>):<p>No verified numeric result imported. Missing scores are not zero.</p>}</div>:measured.length?<div className="reference-grid">{measured.map((r,i)=><article className="reference-card" key={i}><span className="mini-badge">MEASURED · AUDIT REQUIRED</span><h4>{r.system_id}</h4><strong className="reference-value">{r.score}/{r.scale}</strong><p>{r.metric} · {r.split} · {r.evaluation_mode}</p><small>{r.protocol_revision}</small><a href={r.source_url} target="_blank" rel="noreferrer">Run artifact ↗</a></article>)}</div>:<p className="not-run"><strong>Not run on GCP</strong>Matched Gamst and baseline runs will appear here once measured.</p>}
   <details className="atlas-data"><summary>Dataset, preparation & MCP</summary><p><strong>Data:</strong> {b.dataset_size} {b.dataset_url&&<a href={b.dataset_url}>Dataset ↗</a>}</p><p>{b.prepare}</p><p><strong>Limitations:</strong> {b.limitations}</p><p><strong>MCP:</strong> {recipes.some(r=>r.benchmark===b.id)?recipes.filter(r=>r.benchmark===b.id).map(r=>r.id).join(', ')+' — GPU validation pending.':'Reference only; no executable recipe.'} <a href="https://github.com/NomaDamas/Gamst-bench/blob/main/docs/MCP.md">MCP guide ↗</a></p></details>
  </div></section>;
}
