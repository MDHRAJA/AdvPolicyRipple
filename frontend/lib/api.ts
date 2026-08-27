export type Policy = {
  id: string;
  name: string;
  description: string;
  policy_type: string;
  parameters: Record<string, number>;
};

export type Population = { id: string; name: string; synthetic: boolean; observed_context?: boolean };

export type ObservedMetric = {
  dataset: string; geography: string; period: string; metric: string;
  value: number | string; unit: string; source_org: string; source_url: string;
  evidence_type: 'OBSERVED DATA'; notes?: string;
};

export type SourceEntry = {
  name: string;
  years: Array<number | string>;
  integration_status: string;
  publisher: string;
  url: string;
  coverage: string[];
  publication_label?: string;
};

export type SourceCatalog = {
  geography: string;
  evidence_policy: string;
  sources: SourceEntry[];
};

export type ChennaiObserved = {
  geography: string;
  evidence_type: 'OBSERVED DATA';
  metrics: ObservedMetric[];
  sources: SourceCatalog;
};

export type ChennaiAnchor = {
  evidence_type: 'OBSERVED DATA';
  observed_population: number;
  synthetic_sample_size: number;
  people_per_synthetic_agent: number;
  observed_context_variables: string[];
  synthetic_only_variables: string[];
};

export type SimulationConfig = {
  population: { preset: string; size: number; neighborhoods: number };
  policy_id: string;
  policy_parameters: Record<string, number>;
  rounds: number;
  seed: number;
};

export type Metrics = {
  resource_access: number;
  inequality: number;
  stress: number;
  satisfaction: number;
  policy_support: number;
  compliance: number;
  trust: number;
  relocation: number;
  cooperation: number;
};

export const METRIC_LABELS: Record<keyof Metrics, string> = {
  resource_access: 'Resource access',
  inequality: 'Inequality',
  stress: 'Stress',
  satisfaction: 'Satisfaction',
  policy_support: 'Policy support',
  compliance: 'Compliance',
  trust: 'Trust',
  relocation: 'Relocation',
  cooperation: 'Cooperation',
};

export const ADVERSE_METRICS = new Set<keyof Metrics>(['inequality', 'stress', 'relocation']);

export type SimulationResult = {
  simulation_id?: string;
  baseline: Metrics;
  timeline: Array<Metrics & { round: number }>;
  final: Metrics;
  unintended_consequence_score: number;
  observed_data_anchor?: ChennaiAnchor;
  [key: string]: unknown;
};

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const message = await response.text().catch(() => 'Request failed');
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json();
}

export const api = {
  policies: () => request<Policy[]>('/api/policies'),
  populations: () => request<Population[]>('/api/populations'),
  chennaiObserved: () => request<ChennaiObserved>('/api/observed/chennai'),
  chennaiCalibration: (size: number) => request<ChennaiAnchor>(`/api/observed/chennai/calibration?size=${size}`),
  create: (config: SimulationConfig) =>
    request<{ simulation_id: string; status: string }>('/api/simulations', {
      method: 'POST', body: JSON.stringify({ config }),
    }),
  run: (id: string) => request<SimulationResult>(`/api/simulations/${id}/run`, { method: 'POST' }),
  get: (id: string) => request<{ simulation_id: string; config: SimulationConfig; result: SimulationResult | null }>(`/api/simulations/${id}`),
  results: (id: string) => request<SimulationResult>(`/api/simulations/${id}/results`),
  compare: (base_config: SimulationConfig, policies: SimulationConfig[]) =>
    request<{ results: Array<{ policy: string; result: Metrics }> }>('/api/simulations/compare', {
      method: 'POST', body: JSON.stringify({ base_config, policies }),
    }),
  assessment: (config: SimulationConfig) =>
    request<{ expected_outcome: Metrics; best_case: Metrics; worst_case: Metrics; uncertainty: Metrics; evidence_used: string; limitations: string[] }>('/api/assessment', {
      method: 'POST', body: JSON.stringify({ config }),
    }),
};
