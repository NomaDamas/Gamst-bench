import {render,screen,fireEvent,within} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import BenchmarkAtlas,{problems} from './BenchmarkAtlas';
import catalog from '../data/catalog.json';
const row=(name:string)=>screen.getByRole('button',{name:new RegExp('^'+name)});
describe('Benchmark atlas',()=>{
 it('displays imported measured metrics only under their benchmark',()=>{const report={evidence:'measured',official_scores:[{benchmark:'FastBench',system_id:'C',score:12,scale:100,metric:'Timed QA',split:'test',evaluation_mode:'online',source_url:'https://example.com/run',protocol_revision:'abc'}]};render(<BenchmarkAtlas report={report}/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('12/100')).toBeTruthy();fireEvent.click(row('SPOT-Bench'));fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.queryByText('12/100')).toBeNull();expect(screen.getByText('Not run on GCP')).toBeTruthy();});
 it('selecting a matrix row switches the detail panel',()=>{render(<BenchmarkAtlas/>);fireEvent.click(row('SPOT-Bench'));expect(row('SPOT-Bench').getAttribute('aria-pressed')).toBe('true');expect(within(screen.getByRole('region',{name:'SPOT-Bench details'})).getByText('Ctrl-SPOT')).toBeTruthy();});
 it('never presents published references as our measurements',()=>{render(<BenchmarkAtlas/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('Not run on GCP')).toBeTruthy();expect(screen.queryByText('PUBLISHED · NOT REPRODUCED')).toBeNull();});
 it('every catalog coverage key maps to a matrix column',()=>{const ids=new Set(problems.map(p=>p.id));for(const b of catalog.benchmarks)for(const k of Object.keys(b.covers))expect(ids.has(k)).toBe(true);});
});
