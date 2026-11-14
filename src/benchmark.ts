import dataset from '../data/benchmark.json';
export const data = dataset;
export type Model = typeof data.models[number];
export type Category = keyof Model['scores'];
export type Metric = 'overall' | Category;
export type Filters = { query: string; family: string; smallOnly: boolean; selected: string[]; category: Metric };
export const defaults: Filters = { query: '', family: 'All families', smallOnly: false, selected: [], category: 'overall' };
export const colors: Record<string, string> = { GAMST: '#7754d6', Baseline: '#4d9f9b', Reference: '#d19b54' };
export function score(model: Model, category: Metric = 'overall') {
  return category === 'overall' ? Object.values(model.scores).reduce((a, b) => a + b, 0) / data.categories.length : model.scores[category];
}
export function filterModels(filters: Filters, includeSelection = true) {
  return data.models.filter(m => m.name.toLowerCase().includes(filters.query.toLowerCase()) && (filters.family === 'All families' || m.family === filters.family) && (!filters.smallOnly || m.parameters <= 7) && (!includeSelection || !filters.selected.length || filters.selected.includes(m.id)));
}
export function readFilters(search: string): Filters {
  const params = new URLSearchParams(search);
  const category = params.get('category');
  const family = params.get('family');
  return { query: params.get('q') ?? '', family: family && Object.hasOwn(colors, family) ? family : defaults.family, smallOnly: params.get('small') === '1', selected: (params.get('models') ?? '').split(',').filter(id => data.models.some(m => m.id === id)), category: data.categories.some(c => c.id === category) ? category as Category : 'overall' };
}
export function writeFilters(filters: Filters) {
  const params = new URLSearchParams();
  if (filters.query) params.set('q', filters.query);
  if (filters.family !== defaults.family) params.set('family', filters.family);
  if (filters.smallOnly) params.set('small', '1');
  if (filters.selected.length) params.set('models', filters.selected.join(','));
  if (filters.category !== 'overall') params.set('category', filters.category);
  return params.toString();
}
export function csv(models: Model[], category: Metric) {
  const cell = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`;
  const header = ['Data status', 'Release', 'Model', 'Family', 'Parameters (B)', 'Overall', ...data.categories.map(c => c.name), 'USD / 1k clips', 'Latency p50 (s)', 'Selected metric', 'Selected score'];
  return [header, ...models.map(m => [data.isDemo ? 'SYNTHETIC DEMO' : 'MEASURED', data.release, m.name, m.family, m.parameters, score(m).toFixed(1), ...data.categories.map(c => m.scores[c.id as Category]), m.cost, m.latency, category, score(m, category).toFixed(1)])].map(row => row.map(cell).join(',')).join('\r\n');
}
