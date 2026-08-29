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

export type ChennaiWards = { features: Array<{ properties: Record<string, unknown>; geometry: { type: string; coordinates: unknown } }>; evidence_type: 'OBSERVED DATA'; geography: string; period: string; source_org: string; source_url: string; provenance: string; data_boundary: string };
export type WardProfile = { evidence_type: 'OBSERVED DATA'; ward: string; zone?: string; region?: string; assembly_constituency?: string; official_area_square_metres?: number; source_org: string; source_url: string; provenance: string; data_boundary: string };

export type ChennaiAnchor = {
  evidence_type: 'OBSERVED DATA';
  observed_population: number;
  synthetic_sample_size: number;
  people_per_synthetic_agent: number;
  observed_context_variables: string[];
  synthetic_only_variables: string[];
};

export type PolicySelection = { policy_id: string; policy_parameters: Record<string, number> };

export type SimulationConfig = {
  population: { preset: string; size: number; neighborhoods: number };
  policy_id: string;
  policy_parameters: Record<string, number>;
  policy_bundle?: PolicySelection[];
  target_wards?: string[];
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

export type IncomeGroupImpact = { baseline: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'>; final: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'>; change: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'> };

export type AIInterpreterStatus = { configured: 'gemini' | 'rule_based'; display: string; fallback: string };

export type PolicyPlan = { interpretation: string; interpretation_source: 'gemini' | 'rule_based'; assumptions: string[]; objectives: string[]; proposed_config: SimulationConfig; matched_policy: Policy; policy_detail: { parameter: string; value_percent: number; population_basis: string }; recommendation: { recommended: { policy_id: string; name: string; score: number; preview: Metrics; income_groups: Record<'low' | 'middle' | 'high', IncomeGroupImpact>; policy_bundle: Array<{ policy_id: string; name: string; policy_parameters: Record<string, number>; parameter: string; direction: string; value_percent: number; instruction: string }>; implementation: { parameter: string; direction: string; value_percent: number; instruction: string } }; alternatives: Array<{ policy_id: string; name: string; score: number; preview: Metrics; policy_bundle?: Array<{ policy_id: string; name: string }> }>; explanation: string; boundary: string } };

export type WardImpact = { baseline: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'> & { synthetic_agents: number }; final: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'> & { synthetic_agents: number }; change: Pick<Metrics, 'resource_access' | 'stress' | 'trust' | 'compliance'> };

export type SimulationResult = {
  simulation_id?: string;
  baseline: Metrics;
  timeline: Array<Metrics & { round: number }>;
  final: Metrics;
  unintended_consequence_score: number;
  observed_data_anchor?: ChennaiAnchor;
  income_group_impacts?: Record<'low' | 'middle' | 'high', IncomeGroupImpact>;
  ward_impacts?: Record<string, WardImpact>;
  ward_impact_evidence_type?: 'SIMULATION OUTPUT';
  policy_bundle?: string[];
  target_wards?: string[];
  [key: string]: unknown;
};

// Undefined means local development; /backend is used by the Vercel Services deployment.
const API = process.env.NEXT_PUBLIC_API_URL === undefined
  ? 'http://localhost:8000'
  : process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '');

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
  aiStatus: () => request<AIInterpreterStatus>('/api/ai/status'),
  planPolicy: (payload: { prompt: string; objectives: string[]; size: number; rounds: number; seed: number }) => request<PolicyPlan>('/api/ai/policy-plan', { method: 'POST', body: JSON.stringify(payload) }),
  populations: () => request<Population[]>('/api/populations'),
  chennaiObserved: () => request<ChennaiObserved>('/api/observed/chennai'),
  chennaiWards: () => request<ChennaiWards>('/api/observed/chennai/wards'),
  wardProfile: (ward: string) => request<WardProfile>('/api/observed/chennai/wards/' + ward),
  chennaiCalibration: (size: number) => request<ChennaiAnchor>(`/api/observed/chennai/calibration?size=${size}`),
  create: (config: SimulationConfig) =>
    request<{ simulation_id: string; status: string }>('/api/simulations', {
      method: 'POST', body: JSON.stringify({ config }),
    }),
  runSession: (config: SimulationConfig) => request<SimulationResult>('/api/simulations/run', { method: 'POST', body: JSON.stringify({ config }) }),
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
