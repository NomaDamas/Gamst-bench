import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { csv, data, defaults, filterModels, readFilters, score, writeFilters } from './benchmark';
describe('benchmark calculations',()=>{
  it('uses an equal-weight mean and the chosen category without rounding early',()=>{
    const m=data.models[0];expect(score(m)).toBeCloseTo(84.1333333333);expect(score(m,'ocr')).toBe(83.4);
  });
  it('combines filters with AND and selection with OR',()=>{
    expect(filterModels({...defaults,selected:['gamst-3b','reference-32b'],smallOnly:true}).map(m=>m.id)).toEqual(['gamst-3b']);
    expect(filterModels({...defaults,family:'Reference',smallOnly:true})).toHaveLength(0);
  });
  it('round-trips shared filters and discards invalid IDs',()=>{
    const filters={...defaults,query:'GAMST',selected:['gamst-3b'],smallOnly:true,category:'audio' as const};
    expect(readFilters(writeFilters(filters))).toEqual(filters);
    expect(readFilters('?models=nonexistent&category=bad&family=bad')).toEqual(defaults);
  });
  it('exports only selected rows with all six scores and demo provenance',()=>{
    const result=csv(filterModels({...defaults,selected:['gamst-3b']}),'audio');
    expect(result.split('\r\n')).toHaveLength(2);expect(result).toContain('SYNTHETIC DEMO');expect(result).toContain('"audio","78.2"');expect(result).not.toContain('Reference 32B');
  });
});
describe('linked dashboard',()=>{
  it('filters every chart and table when a scatter point is selected, then resets',async()=>{
    const user=userEvent.setup();render(<App/>);
    await user.click(screen.getByRole('button',{name:'Filter by GAMST 3B'}));
    expect(screen.getByText('1 of 8 models')).toBeTruthy();
    expect(screen.getAllByRole('button',{name:/in ranking$/})).toHaveLength(1);
    expect(screen.getAllByRole('checkbox',{name:/Compare /})).toHaveLength(1);
    expect(screen.getByText('84.1',{selector:'.stat-value'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Filter by Audio understanding'}).textContent).toContain('78.2');
    await user.click(screen.getByRole('button',{name:'Reset'}));
    expect(screen.getAllByRole('button',{name:/in ranking$/})).toHaveLength(8);
  });
  it('links ranking, comparison controls and category selection',async()=>{
    const user=userEvent.setup();render(<App/>);
    await user.click(screen.getByRole('button',{name:'Select GAMST 3B in ranking'}));
    await user.click(screen.getByRole('button',{name:'+ GAMST 7B'}));
    expect(screen.getByText('2 of 8 models')).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Filter by Audio understanding'}));
    expect(screen.getByText('TOP AUDIO SCORE')).toBeTruthy();
    expect(screen.getByText('84.1',{selector:'.stat-value'})).toBeTruthy();
    expect(window.location.search).toContain('category=audio');
  });
  it('handles empty results and disables export, then restores results',async()=>{
    const user=userEvent.setup();render(<App/>);
    await user.type(screen.getByRole('textbox',{name:'Search models'}),'no-such-model');
    expect(screen.getByText('0 of 8 models')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Export results'}) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole('button',{name:'Clear search'}));
    expect(screen.getByText('8 of 8 models')).toBeTruthy();
  });
  it('restores a shared view, supports keyboard selection and sorts cost numerically',async()=>{
    window.history.replaceState(null,'','/?family=GAMST&small=1');
    const user=userEvent.setup();render(<App/>);
    expect(screen.getByText('3 of 8 models')).toBeTruthy();
    const point=screen.getByRole('button',{name:'Filter by GAMST 1B'});point.focus();await user.keyboard('{Enter}');
    expect(screen.getByText('1 of 8 models')).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Reset'}));
    await user.click(screen.getByRole('button',{name:'Cost / 1k'}));
    const rows=within(screen.getByRole('table')).getAllByRole('row');
    expect(rows[1].textContent).toContain('GAMST 1B');
  });
});
