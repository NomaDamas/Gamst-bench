import {render,screen,fireEvent,within} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import BenchmarkAtlas from './BenchmarkAtlas';
describe('Benchmark atlas',()=>{
 it('switches linked problem, results and dataset panels with keyboard support',()=>{render(<BenchmarkAtlas/>);expect(screen.getAllByRole('tab')).toHaveLength(9);fireEvent.keyDown(screen.getByRole('tab',{name:'FastBench'}),{key:'ArrowRight'});expect(screen.getByRole('tab',{name:'SPOT-Bench'}).getAttribute('aria-selected')).toBe('true');expect(within(screen.getByRole('tabpanel')).getByText('Ctrl-SPOT')).toBeTruthy();});
 it('never presents published references as our measurements',()=>{render(<BenchmarkAtlas/>);fireEvent.click(screen.getByRole('button',{name:'Our GCP runs'}));expect(screen.getByText('Not run on GCP')).toBeTruthy();expect(screen.queryByText('PUBLISHED · NOT REPRODUCED')).toBeNull();});
 it('shows a text-evidence LLM architecture and switches to selective VLM',()=>{render(<BenchmarkAtlas/>);expect(screen.getByLabelText('Gamst + LLM architecture').textContent).toContain('Thin perception');fireEvent.click(screen.getByRole('button',{name:'Gamst + VLM + LLM'}));expect(screen.getByLabelText('Gamst + VLM + LLM architecture').textContent).toContain('Selective VLM');});
});
