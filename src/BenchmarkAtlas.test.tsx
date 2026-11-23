import {render,screen,fireEvent,within} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import BenchmarkAtlas,{problems} from './BenchmarkAtlas';
import type {Campaign} from './BenchmarkAtlas';
import catalog from '../data/catalog.json';
const row=(name:string)=>screen.getByRole('button',{name:new RegExp('^'+name)});
const none:Campaign={id:'none',title:'None',hardware:'-',source_url:'https://example.com/none',benchmarks:{}};
const devRun:Campaign={id:'dev',title:'Dev campaign',hardware:'1× L4',source_url:'https://example.com/report',benchmarks:{fastbench:{split:'dev50',metric:'final score',arms:[
 {arm:'A',system:'Native',track:'native-protocol',score:41.2,scale:100,backbone_calls:900,prompt_tokens:null},
 {arm:'C',system:'GAMST',track:'gamst-extension',score:null,scale:100,backbone_calls:null,prompt_tokens:null,note:'failed run kept'}]}}};
describe('Benchmark atlas',()=>{
 it('displays imported measured metrics only under their benchmark',()=>{const report={evidence:'measured',official_scores:[{benchmark:'FastBench',system_id:'C',score:12,scale:100,metric:'Timed QA',split:'test',evaluation_mode:'online',source_url:'https://example.com/run',protocol_revision:'abc'}]};render(<BenchmarkAtlas report={report} campaign={none}/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('12/100')).toBeTruthy();fireEvent.click(row('OmniPro'));fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.queryByText('12/100')).toBeNull();expect(screen.getByText('Not run on GCP')).toBeTruthy();});
 it('shows dev-subset campaign arms only under their benchmark, labelled by track',()=>{render(<BenchmarkAtlas campaign={devRun}/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('41.2/100')).toBeTruthy();expect(screen.getByText('NATIVE PROTOCOL · DEV SUBSET')).toBeTruthy();expect(screen.getByText('GAMST EXTENSION · DEV SUBSET')).toBeTruthy();expect(screen.getByText('Not scored')).toBeTruthy();fireEvent.click(row('OmniPro'));fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.queryByText('41.2/100')).toBeNull();expect(screen.getByText('Not run on GCP')).toBeTruthy();});
 it('selecting a matrix row switches the detail panel',()=>{render(<BenchmarkAtlas/>);fireEvent.click(row('OmniPro'));expect(row('OmniPro').getAttribute('aria-pressed')).toBe('true');expect(within(screen.getByRole('region',{name:'OmniPro details'})).getByText('Gemini-3-Flash')).toBeTruthy();});
 it('never presents published references as our measurements',()=>{render(<BenchmarkAtlas campaign={none}/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('Not run on GCP')).toBeTruthy();expect(screen.queryByText('PUBLISHED · NOT REPRODUCED')).toBeNull();});
 it('every catalog coverage key maps to a matrix column',()=>{const ids=new Set(problems.map(p=>p.id));for(const b of catalog.benchmarks)for(const k of Object.keys(b.covers))expect(ids.has(k)).toBe(true);});
});
