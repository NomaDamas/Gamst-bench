import fs from 'node:fs';
const c=JSON.parse(fs.readFileSync('data/catalog.json','utf8'));
const ids=new Set();
for(const b of c.benchmarks){
 if(ids.has(b.id))throw Error('Duplicate benchmark');ids.add(b.id);
 for(const u of [b.source_url,b.dataset_url,...b.results.map(r=>r.source_url)].filter(Boolean))if(new URL(u).protocol!=='https:')throw Error('Invalid source URL');
 for(const r of b.results)if(r.evidence!=='published'||!Number.isFinite(r.value)||!r.scope||!r.metric)throw Error('Unscoped reference result');
}
const lines=['<!-- BENCHMARKS:START -->','## Benchmark atlas','',`Reviewed ${c.reviewed_at}. Published snapshots are **not reproduced**, not a live SOTA ranking and not comparable across protocols. All Gamst hybrid runs remain **not run**. No inference or dataset downloads run locally.`, '', '[Interactive comparison tabs](https://gamst-bench.jinminseong.com/#benchmarks) · [Matched evaluation plan](docs/COMPARISONS.md) · [GCP preparation](infra/gcp/README.md)',''];
for(const b of c.benchmarks){lines.push(`### ${b.name} · ${b.venue}`,'',`[Official source](${b.source_url})${b.dataset_url?` · [Dataset](${b.dataset_url})`:''}`,'',`- **Problem:** ${b.problem}`,`- **Existing approach:** ${b.existing}`,`- **Gamst hypothesis (untested):** ${b.gamst}`,`- **Metrics:** ${b.metric}`,`- **Data:** ${b.dataset_size}. ${b.prepare}`,`- **Limits:** ${b.limitations}`,`- **Integration:** ${b.integration}; phase ${b.phase}.`,'');for(const r of b.results)lines.push(`- Published: **${r.model} — ${r.value}${r.unit} ${r.metric}**. ${r.scope} [Source](${r.source_url}).`);if(!b.results.length)lines.push('No verified numeric result imported.');lines.push('');}
lines.push('### Planned comparison arms','');for(const a of c.arms)lines.push(`- **${a.name}**: ${a.path.join(' → ')}. ${a.role} Status: not run.`);lines.push('','### Readiness','',`GCP only. Status: **${c.readiness.status}**. [Pinned Gamst readiness source](${c.readiness.gamst_source}).`,'',...c.readiness.requirements.map(r=>'- '+r),'','<!-- BENCHMARKS:END -->');
const p='README.md',old=fs.readFileSync(p,'utf8'),block=lines.join('\n');const next=old.includes('<!-- BENCHMARKS:START -->')?old.replace(/<!-- BENCHMARKS:START -->[\s\S]*?<!-- BENCHMARKS:END -->/,block):old.trimEnd()+'\n\n'+block+'\n';
if(process.argv.includes('--check')){if(old!==next)throw Error('README catalog out of sync');console.log('Benchmark catalog and README verified');}else fs.writeFileSync(p,next);
