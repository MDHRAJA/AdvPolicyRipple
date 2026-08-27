'use client';

import { useRouter } from 'next/navigation';

const scenarios = [
  { id: 'water', title: 'Water Stress', policy: 'Water Rationing', description: 'Apply a 25% water reduction and inspect access, stress, trust and cooperation.', preset: 'Balanced City', parameter: '25% reduction', tag: 'Resource scarcity' },
  { id: 'housing', title: 'Affordable Housing', policy: 'Rent / Zoning Change', description: 'Model a housing cost change in a more unequal city and examine how access and inequality respond.', preset: 'Unequal City', parameter: '−15% cost change', tag: 'Housing' },
  { id: 'transport', title: 'Public Transport Subsidy', policy: 'Public Transport Subsidy', description: 'Test a targeted mobility subsidy in a dense synthetic city and inspect access and institutional outcomes.', preset: 'High-Density City', parameter: '15% subsidy', tag: 'Mobility' },
  { id: 'energy', title: 'Energy Rationing', policy: 'Energy Rationing', description: 'Stress-test constrained energy availability and observe downstream effects of scarcity.', preset: 'High-Density City', parameter: '20% reduction', tag: 'Resource scarcity' },
];

export default function Scenarios() {
  const router = useRouter();
  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">Scenario library</div><h1>Start with a policy experiment.</h1><p>Each scenario is a real simulator preset. Open one to inspect assumptions, change parameters, and run it.</p></div><button className="btn" onClick={() => router.push('/simulate')}>Build from scratch →</button></div>
    <div className="scenario-grid">{scenarios.map((scenario, index) => <article className="scenario-card card" key={scenario.id}>
      <div className="scenario-top"><span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><span className="pill">{scenario.tag}</span></div>
      <h2>{scenario.title}</h2><p>{scenario.description}</p>
      <div className="scenario-meta"><div><span>Policy</span><b>{scenario.policy}</b></div><div><span>Population</span><b>{scenario.preset}</b></div><div><span>Parameter</span><b>{scenario.parameter}</b></div></div>
      <button className="btn primary" onClick={() => router.push(`/simulate?scenario=${scenario.id}`)}>Load scenario →</button>
    </article>)}</div>
    <section className="card p-6 scenario-note"><div><div className="label">Why presets?</div><h2>Comparable starting points.</h2></div><p>Presets keep the first experiment reproducible while leaving the policy, population size, rounds and seed editable. Trust and cooperation are synthetic behavioural states that respond to policy experience and local interactions—not observed measures of real people.</p></section>
  </main>;
}
