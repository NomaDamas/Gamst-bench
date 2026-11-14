import {describe,it,expect} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import {data,defaults,filterRows,readFilters,writeFilters,summarize,pareto,csv} from './benchmark';
describe('evaluation explorer calculations',()=>{
 it('computes the same unfiltered scores as the Python evaluator',()=>{
  const a=summarize(data.rows.filter(r=>r.system_id==='A'));
  expect(a.n).toBe(36);expect(a.costHour).toBeCloseTo(3.12);expect(a.success).toBe(0);
  const c=summarize(data.rows.filter(r=>r.system_id==='C'));
  expect(c.success).toBeCloseTo(35/36);expect(c.critical).toBeCloseTo(35/36);
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
  expect(new Set(filterRows({...defaults,budget:'1'}).map(r=>r.system_id))).toEqual(new Set(['B','C']));
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
 it('links cost chart selection with all charts, table and KPIs',async()=>{
  const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Filter by GAMST hybrid'}));
  expect(screen.getByText('1 configurations · 36 task runs')).toBeTruthy();expect(screen.getAllByRole('checkbox',{name:/Compare /})).toHaveLength(1);
  expect(screen.getAllByText('97.2%',{selector:'.stat-value'})).toHaveLength(2);
  await user.click(screen.getByRole('button',{name:'Reset'}));expect(screen.getAllByRole('checkbox',{name:/Compare /})).toHaveLength(4);
 });
 it('links suite and duration filters with the task inspector',async()=>{
  const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Filter suite Memory'}));
  expect(screen.getByText('4 configurations · 24 task runs')).toBeTruthy();
  await user.click(screen.getByRole('button',{name:'Filter short events'}));expect(screen.getByText('4 configurations · 8 task runs')).toBeTruthy();
  expect(within(screen.getByRole('combobox',{name:'Inspect task'})).getAllByRole('option')).toHaveLength(2);
 });
 it('shows measured evidence as empty and disables export',async()=>{
  const user=userEvent.setup();render(<App/>);await user.selectOptions(screen.getByRole('combobox',{name:'Evidence'}),'measured');
  expect(screen.getByText('0 configurations · 0 task runs')).toBeTruthy();expect((screen.getByRole('button',{name:'Export'}) as HTMLButtonElement).disabled).toBe(true);
 });
 it('restores shared filters and supports keyboard chart selection',async()=>{
  history.replaceState(null,'','/?suite=revision');const user=userEvent.setup();render(<App/>);
  const curve=screen.getByRole('button',{name:'Select GAMST hybrid curve'});curve.focus();await user.keyboard('{Enter}');
  expect(screen.getByText('1 configurations · 6 task runs')).toBeTruthy();expect(location.search).toContain('systems=C');
 });
 it('keeps frozen acceptance distinct from exploratory filtering',async()=>{
  const user=userEvent.setup();render(<App/>);await user.click(screen.getByRole('button',{name:'Filter by Thin models only'}));
  expect(screen.getAllByText('Not passed')).toHaveLength(2);expect(screen.getByText(/Full preregistered experiment/)).toBeTruthy();
 });
});
