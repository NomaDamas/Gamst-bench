import {describe,it,expect} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import {data,primary,defaults,filterRows,readFilters,writeFilters,summarize,pareto,csv} from './benchmark';
describe('evaluation explorer calculations',()=>{
 it('computes the same unfiltered scores as the Python evaluator',()=>{
  for(const s of data.systems){const m=summarize(data.rows.filter(r=>r.system_id===s.id));const py=data.summaries[s.id];
   expect(m.n).toBe(36);expect(m.success).toBeCloseTo(py.success_rate);expect(m.costHour).toBeCloseTo(py.cost_per_hour!);expect(m.p95).toBe(py.p95_ms);}
 });
 it('keeps budget-sweep configurations out of the matched explorer',()=>{
  expect(primary.map(s=>s.id)).toEqual(['A','B','C','D','E']);
  expect(new Set(filterRows(defaults).map(r=>r.system_id))).toEqual(new Set(['A','B','C','D','E']));
  expect(readFilters('?systems=C3').selected).toEqual([]);
 });
 it('keeps unknown cost and context latency unknown',()=>{
  const row={...data.rows[0],cost_usd:null,context_latency_ms:null};expect(summarize([row]).costHour).toBeNull();expect(summarize([row]).contextP95).toBeNull();
 });
 it('uses task denominators and never lets a deadline rescue a wrong answer',()=>{
  const row={...data.rows[0],quality:0,latency_ms:100};expect(summarize([row],10000).success).toBe(0);
 });
 it('combines filters and excludes unknown costs from finite budgets',()=>{
  expect(filterRows({...defaults,evidence:'measured'})).toHaveLength(0);
  expect(filterRows({...defaults,selected:['A','C'],suite:'memory'})).toHaveLength(12);
  expect(new Set(filterRows({...defaults,budget:'2'}).map(r=>r.system_id))).toEqual(new Set(['B','C','D']));
 });
 it('round-trips valid URL state and rejects invalid fields',()=>{
  const f={...defaults,suite:'memory',selected:['C'],deadline:3000,policy:'hybrid'};expect(readFilters(writeFilters(f))).toEqual(f);
  expect(readFilters('?systems=bad&deadline=-1&suite=nope')).toEqual(defaults);
 });
 it('calculates a nondominated frontier and excludes unknowns',()=>{
  expect(pareto([{id:'A',cost:2,success:.8},{id:'B',cost:1,success:.9},{id:'C',cost:null,success:1}])).toEqual(['B']);
 });
 it('exports task evidence, deadline and trace identity',()=>{
  const result=csv(data.rows.slice(0,1),2000);expect(result.split('\r\n')).toHaveLength(2);expect(result).toContain('synthetic');expect(result).toContain(data.rows[0].trace_sha256);
 });
});
describe('cross-filtered dashboard',()=>{
 const openResults=(search='')=>history.replaceState(null,'','/'+search+'#results');
 it('overview frontier click opens results filtered to that pipeline',async()=>{
  history.replaceState(null,'','/');const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Filter by GAMST hybrid'}));
  expect(location.hash).toBe('#results');expect(screen.getByText('1 configurations · 36 task runs')).toBeTruthy();expect(screen.getAllByRole('checkbox',{name:/Compare /})).toHaveLength(1);
  expect(screen.getAllByText('97.2%',{selector:'.stat-value'})).toHaveLength(2);
  await user.click(screen.getByRole('button',{name:'Reset'}));expect(screen.getAllByRole('checkbox',{name:/Compare /})).toHaveLength(5);
 });
 it('links suite and duration filters with the task inspector',async()=>{
  openResults();const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Filter suite Memory'}));
  expect(screen.getByText('5 configurations · 30 task runs')).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Diagnostics'}));await user.click(screen.getByRole('button',{name:'Filter short events'}));expect(screen.getByText('5 configurations · 10 task runs')).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Traces'}));expect(within(screen.getByRole('combobox',{name:'Inspect task'})).getAllByRole('option')).toHaveLength(2);
 });
 it('shows measured evidence as empty and disables export',async()=>{
  openResults();const user=userEvent.setup();render(<App/>);await user.selectOptions(screen.getByRole('combobox',{name:'Evidence'}),'measured');
  expect(screen.getByText('0 configurations · 0 task runs')).toBeTruthy();expect((screen.getByRole('button',{name:'Export'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('restores shared filters and supports keyboard chart selection',async()=>{
  openResults('?suite=revision');const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Diagnostics'}));
  const curve=screen.getByRole('button',{name:'Select GAMST hybrid curve'});curve.focus();await user.keyboard('{Enter}');
  expect(screen.getByText('1 configurations · 6 task runs')).toBeTruthy();expect(location.search).toContain('systems=C');
 });
 it('keeps frozen acceptance distinct from exploratory filtering',async()=>{
  openResults('?systems=B');const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('tab',{name:'Method'}));
  expect(location.search).toContain('systems=B');expect(screen.getAllByText('Not passed')).toHaveLength(3);expect(screen.getByText(/Preregistered; independent of any filter/)).toBeTruthy();
 });
});
