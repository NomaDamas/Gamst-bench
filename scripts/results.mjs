import { readFileSync, writeFileSync } from 'node:fs';
const data = JSON.parse(readFileSync(new URL('../data/benchmark.json', import.meta.url), 'utf8'));
const fail = message => { throw new Error(`Invalid benchmark data: ${message}`); };
if (typeof data.isDemo !== 'boolean' || !/^\d{4}-\d{2}-\d{2}$/.test(data.release)) fail('release / isDemo');
if (!data.categories?.length || !data.models?.length) fail('empty categories or models');
const categories = data.categories.map(c => c.id);
if (new Set(categories).size !== categories.length) fail('duplicate category IDs');
if (new Set(data.models.map(m=>m.id)).size !== data.models.length) fail('duplicate model IDs');
for (const m of data.models) {
  for (const key of ['cost','latency','parameters']) if (!Number.isFinite(m[key]) || m[key] < 0) fail(`${m.id}: ${key}`);
  for (const id of categories) if (!Number.isFinite(m.scores[id]) || m.scores[id] < 0 || m.scores[id] > 100) fail(`${m.id}: ${id}`);
  if (Object.keys(m.scores).length !== categories.length) fail(`${m.id}: unexpected score category`);
  if (!m.name || !m.id || !['GAMST','Baseline','Reference'].includes(m.family)) fail(`${m.id}: name / id / family`);
}
const score = m => categories.reduce((sum,c)=>sum+m.scores[c],0)/categories.length;
const escape = value => String(value).replaceAll('|','\\|').replaceAll('\n',' ');
const headers = ['Rank','Model','Family','Params (B)','Overall',...data.categories.map(c=>c.short),'Cost / 1k clips (USD)','p50 latency (s)'];
const rows = [...data.models].sort((a,b)=>score(b)-score(a)).map((m,i)=>[i+1,m.name,m.family,m.parameters,score(m).toFixed(1),...categories.map(c=>m.scores[c].toFixed(1)),m.cost.toFixed(2),m.latency.toFixed(2)]);
const line = cells => `| ${cells.map(escape).join(' | ')} |`;
const block = `<!-- RESULTS:START -->\n\n> ${data.isDemo?'**SYNTHETIC DEMO — 실제 벤치마크 결과 아님. 모델과 수치는 모두 가상입니다.**':'Measured benchmark results — 평가 프로토콜과 실행 증빙을 함께 확인하세요.'}\n\nRelease: **${data.release}** · ${data.models.length} models · ${categories.length} dimensions\n\n${[line(headers),line(headers.map(()=> '---')),...rows.map(line)].join('\n')}\n\nGenerated from [data/benchmark.json](data/benchmark.json) using \`npm run results\`.\n\n<!-- RESULTS:END -->`;
const path = new URL('../README.md',import.meta.url);
const previous = readFileSync(path,'utf8');
if (!previous.includes('<!-- RESULTS:START -->') || !previous.includes('<!-- RESULTS:END -->')) fail('README markers missing');
const next = previous.replace(/<!-- RESULTS:START -->[\s\S]*?<!-- RESULTS:END -->/,block);
if (process.argv.includes('--check')) { if (next !== previous) {console.error('README results are stale. Run npm run results.');process.exitCode=1;} else console.log('Dataset valid; README results match.'); }
else {writeFileSync(path,next);console.log('Dataset valid; README results updated.');}
