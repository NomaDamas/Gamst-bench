import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const data=JSON.parse(execFileSync('python3',['scripts/evaluate_release.py'],{encoding:'utf8',maxBuffer:16*1024*1024}));
const reportPath=new URL('../data/benchmark.json',import.meta.url);
const previousReport=JSON.parse(readFileSync(reportPath,'utf8'));
const pct=v=>v==null?'Unknown':(v*100).toFixed(1)+'%';
const num=v=>v==null?'Unknown':v.toFixed(2);
const line=cells=>'| '+cells.map(v=>String(v).replaceAll('|','\\|').replaceAll('\n',' ')).join(' | ')+' |';
const headers=['Configuration','Policy','Runs','Grounded & on time','Critical recall','Answer p95 (ms)','Full pipeline USD/h','Evidence'];
const rows=data.systems.map(s=>{const m=data.summaries[s.id];return [s.id+' · '+s.name,s.policy,m.tasks,pct(m.success_rate),pct(m.critical_recall),m.p95_ms,num(m.cost_per_hour),data.evidence];});
const gates=data.comparisons.map(c=>`- **${c.candidate} vs ${c.baseline}: ${c.status}** — cost ratio ${num(c.point.cost_ratio)}, p95 ratio ${num(c.point.latency_ratio)}, quality difference ${num(c.point.quality_delta)}; ${c.clusters} session clusters.`).join('\n');
const official=data.official_scores.length?data.official_scores.map(s=>`- ${s.benchmark} · ${s.system_id}: ${s.score}/${s.scale} · protocol ${s.protocol_revision}`).join('\n'):'Official FastBench / SPOT-Bench / Inf-Streams-Eval: **not measured**.';
const block=`<!-- RESULTS:START -->\n\n> **${data.evidence==='synthetic'?'SYNTHETIC — 합성 프로토콜 검증. 실제 모델 성능·절감 효과를 증명하지 않습니다.':'MEASURED — 외부 채점 및 측정 기록. 독립 감사 필요.'}**\n\nRelease ${data.release} · ${data.protocol} · ${data.rows.length} configuration-task runs\n\n${[line(headers),line(headers.map(()=>'---')),...rows.map(line)].join('\n')}\n\n${gates}\n\n${official}\n\nFrozen plan SHA256: \`${data.plan_sha256}\`\n\nSource manifest: [data/release.json](data/release.json). Generated with \`npm run results\`.\n\n<!-- RESULTS:END -->`;
const readme=new URL('../README.md',import.meta.url);const old=readFileSync(readme,'utf8');
if(!old.includes('<!-- RESULTS:START -->')||!old.includes('<!-- RESULTS:END -->'))throw Error('Missing README result markers');
const next=old.replace(/<!-- RESULTS:START -->[\s\S]*?<!-- RESULTS:END -->/,block);
const normalize=v=>JSON.stringify(v,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))):value);
if(process.argv.includes('--check')){if(next!==old||normalize(data)!==normalize(previousReport)){console.error('Public report or README is stale. Run npm run results.');process.exitCode=1;}else console.log('Frozen sources, public report and README match.');}
else{writeFileSync(reportPath,JSON.stringify(data,null,2)+'\n');writeFileSync(readme,next);console.log('Recomputed public report and README from source traces.');}
