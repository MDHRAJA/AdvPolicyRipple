'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, Metrics, SimulationConfig, SimulationResult } from '@/lib/api';

const labels: Record<keyof Metrics, string> = { resource_access: 'Resource access', inequality: 'Inequality', stress: 'Stress', satisfaction: 'Satisfaction', policy_support: 'Policy support', compliance: 'Compliance', trust: 'Trust', relocation: 'Relocation', cooperation: 'Cooperation' };

type Assessment = { expected_outcome: Metrics; best_case: Metrics; worst_case: Metrics; uncertainty: Metrics; evidence_used: string; limitations: string[] };

export default function ResultsPage() {
  const router = useRouter();
  const [id, setId] = useState('');
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    const requested = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('id') : null;
    const saved = typeof window !== 'undefined' ? window.sessionStorage.getItem('policyforge:lastSimulationId') : null;
    setId(requested || saved || '');
  }, []);

  useEffect(() => {
    if (!id) { setBusy(false); return; }
    setBusy(true); setError('');
    api.get(id).then((data) => {
      if (!data.result) throw new Error('This simulation has not been run yet.');
      setConfig(data.config); setResult(data.result);
      return api.assessment(data.config);
    }).then(setAssessment).catch((e) => setError(e instanceof Error ? e.message : 'Could not load results.')).finally(() => setBusy(false));
  }, [id]);

  if (busy) return <main className="page-shell"><div className="loading-card">Loading results…</div></main>;
  if (error || !result || !config) return <main className="page-shell"><div className="empty-result card p-8"><div className="label">Results</div><h1>{error || 'No simulation selected.'}</h1><p>Run a scenario first, then return here for the full analysis.</p><button className="btn primary" onClick={() => router.push('/simulate')}>Open simulator →</button></div></main>;

  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">Results & assessment</div><h1>Understand the policy effects.</h1><p>Five additional seeded runs estimate the uncertainty range around this synthetic scenario.</p></div><button className="btn" onClick={() => router.push('/simulate')}>← New experiment</button></div>
    <section className="assessment-hero card"><div><div className="label">Policy assessment</div><h2>{result.unintended_consequence_score >= 65 ? 'High impact' : result.unintended_consequence_score >= 50 ? 'Moderate impact' : 'Lower impact'}</h2><p>This synthetic assessment summarizes likely trade-offs under the selected assumptions. Review the trajectory graph and uncertainty range below.</p></div><div className="assessment-score"><span>Unintended consequence</span><b>{Number(result.unintended_consequence_score).toFixed(2)}</b></div></section><div className="assessment-grid"><section className="card p-6"><div className="label">Who is affected?</div><h2 className="section-title">Income-group effects</h2>{result.income_group_impacts ? <div className="income-results">{(['low', 'middle', 'high'] as const).map((group) => <IncomeImpactRow key={group} group={group} impact={result.income_group_impacts![group]} />)}</div> : <p className="helper">Income-group effects are available for new simulation runs.</p>}<p className="helper">Changes are measured from each synthetic group’s starting point. A negative stress change is favourable; these are not observed predictions about real people.</p></section><section className="card p-6"><div className="label">Key outcomes</div><h2 className="section-title">Policy signal</h2><div className="outcome-row"><span>Stress</span><b>{((result.final.stress - result.baseline.stress) * 100).toFixed(1)}%</b></div><div className="outcome-row"><span>Trust</span><b>{((result.final.trust - result.baseline.trust) * 100).toFixed(1)}%</b></div><div className="outcome-row"><span>Compliance</span><b>{(result.final.compliance * 100).toFixed(0)}%</b></div><div className="policy-note"><b>⚠ Unintended consequences</b><span>Score is a synthetic-model summary, not a policy implementation verdict.</span></div></section></div><section className="card p-6 mb-6"><div className="result-hero"><div><div className="label">Experiment</div><h2 className="section-title">{config.policy_id.replaceAll('_', ' ')}</h2><p className="helper">{config.population.preset} · {config.population.size.toLocaleString()} agents · {config.rounds} rounds · seed {config.seed}</p></div><div className="score"><span>Unintended consequence</span><b>{Number(result.unintended_consequence_score).toFixed(2)}</b></div></div>{result.observed_data_anchor && <div className="policy-note result-anchor"><b>OBSERVED DATA ANCHOR · Chennai Census 2011</b><span>{result.observed_data_anchor.observed_population.toLocaleString()} observed people; individual agent behaviour remains synthetic.</span></div>}<div className="metric-grid">{(Object.keys(labels) as Array<keyof Metrics>).map((key) => <Metric key={key} label={labels[key]} value={result.final[key]} />)}</div></section>
    <div className="analysis-grid">
      <section className="card p-6"><div className="label">Trajectory</div><h2 className="section-title">How outcomes evolved</h2><div className="large-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={result.timeline}><XAxis dataKey="round" stroke="#71839a"/><YAxis domain={[0, 1]} stroke="#71839a"/><Tooltip contentStyle={{ background: '#0b1727', border: '1px solid #263e58', borderRadius: 10 }}/><Line type="monotone" dataKey="resource_access" stroke="#52d3b4" strokeWidth={2.5} dot={false}/><Line type="monotone" dataKey="inequality" stroke="#c084fc" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="stress" stroke="#f59e0b" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="trust" stroke="#60a5fa" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div><div className="legend-row"><span>Resource</span><span>Inequality</span><span>Stress</span><span>Trust</span></div></section>
      <section className="card p-6"><div className="label">Uncertainty</div><h2 className="section-title">Expected range</h2>{assessment ? <div className="range-list">{(Object.keys(labels) as Array<keyof Metrics>).map((key) => <div className="range-row" key={key}><div><b>{labels[key]}</b><span>{(assessment.worst_case[key] * 100).toFixed(1)}% — {(assessment.best_case[key] * 100).toFixed(1)}%</span></div><strong>{`${(assessment.expected_outcome[key] * 100).toFixed(1)}%`}</strong><div className="range-track"><i style={{ left: `${assessment.worst_case[key] * 100}%`, width: `${assessment.uncertainty[key] * 100}%` }} /></div></div>)}</div> : <p className="helper">Calculating uncertainty…</p>}</section>
    </div>
    <section className="card p-6 mt-6"><div className="label">Interpretation</div><h2 className="section-title">Decision-support notes</h2><div className="notes-grid"><div><h3>What this says</h3><p>The simulation shows how the selected policy interacts with a synthetic population over time. Higher inequality and stress are treated as adverse outcomes; resource access, trust and compliance are treated as beneficial outcomes.</p></div><div><h3>What this does not say</h3><p>This is not an empirical prediction of real people. The assessment is generated from five seeded simulation runs and inherits every assumption in the synthetic model.</p></div><div><h3>Evidence</h3><p>{assessment?.evidence_used || 'Synthetic simulation evidence.'}</p></div></div>{assessment && <ul className="limitations">{assessment.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}</section>
  </main>;
}

function IncomeImpactRow({ group, impact }: { group: 'low' | 'middle' | 'high'; impact: NonNullable<SimulationResult['income_group_impacts']>['low'] }) {
  const title = group === 'low' ? 'Low income' : group === 'middle' ? 'Middle income' : 'High income';
  return <div className="income-impact-result"><b>{title}</b><span>Access {formatDelta(impact.change.resource_access)} · Stress {formatDelta(impact.change.stress)} · Trust {formatDelta(impact.change.trust)} · Compliance {formatDelta(impact.change.compliance)}</span></div>;
}

function formatDelta(value: number) { return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} pp`; }

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><b>{(Number(value) * 100).toFixed(1)}%</b><div className="metric-bar"><i style={{ width: `${Math.max(0, Math.min(100, Number(value) * 100))}%` }} /></div></div>; }
