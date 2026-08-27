'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, PolicyPlan } from '@/lib/api';

const objectives = [
  ['improve_access', 'Improve access'],
  ['reduce_stress', 'Reduce stress'],
  ['reduce_inequality', 'Reduce inequality'],
  ['build_trust', 'Build trust'],
  ['improve_compliance', 'Improve compliance'],
] as const;

export default function PlannerPage() {
  const router = useRouter();
  const [prompt, setPrompt] = useState('Water shortages are affecting low-income Chennai households. Explore a fair 25% response.');
  const [selected, setSelected] = useState<string[]>(['improve_access', 'reduce_stress', 'reduce_inequality']);
  const [plan, setPlan] = useState<PolicyPlan | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  function toggle(id: string) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  async function interpret() {
    setBusy(true); setError('');
    try { setPlan(await api.planPolicy({ prompt, objectives: selected, size: 10000, rounds: 20, seed: 42 })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not interpret this policy request.'); }
    finally { setBusy(false); }
  }
  function apply() {
    if (!plan) return;
    const config = encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(plan.proposed_config)))));
    router.push(`/simulate?config=${config}`);
  }

  return <main className="page-shell planner-page">
    <div className="page-heading"><div><div className="label">AI-assisted policy planning</div><h1>Describe the problem in your own words.</h1><p>PolicyForge turns your description into a reviewable simulation proposal, then ranks existing policy options against the objectives you choose.</p></div></div>
    <div className="planner-grid">
      <section className="card p-6">
        <div className="label">01 · Policy question</div>
        <textarea className="planner-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-label="Policy problem description" />
        <div className="label planner-label">02 · What matters most?</div>
        <div className="objective-list">{objectives.map(([id, label]) => <button key={id} className={`chip ${selected.includes(id) ? 'active' : ''}`} onClick={() => toggle(id)}>{label}</button>)}</div>
        <button className="btn primary planner-run" onClick={interpret} disabled={busy}>{busy ? 'INTERPRETING…' : 'INTERPRET POLICY →'}</button>
        {error && <div className="error-box">{error}</div>}
        <p className="helper">The interpretation is transparent and rule-based in this version. Review every proposed setting before simulation.</p>
      </section>
      <section className="card p-6">
        <div className="label">02 · AI policy brief</div>
        {!plan ? <div className="planner-empty"><span>✦</span><h2>Waiting for a policy question.</h2><p>Describe a local problem, choose priorities, and PolicyForge will create a simulation-ready proposal.</p></div> : <>
          <h2 className="section-title">{plan.matched_policy.name}</h2>
          <p className="helper">{plan.interpretation}</p>
          <div className="plan-summary"><div><span>Population basis</span><b>{plan.policy_detail.population_basis}</b></div><div><span>Agents</span><b>10,000</b></div><div><span>Rounds</span><b>{plan.proposed_config.rounds}</b></div></div><div className="policy-note"><b>Proposed policy · {plan.matched_policy.name}</b><span>{plan.matched_policy.description} Parameter: {plan.policy_detail.parameter.replaceAll('_', ' ')} at {plan.policy_detail.value_percent}%.</span></div><div className="policy-note"><b>Why this was selected</b><span>Objectives: {plan.objectives.map((item) => item.replaceAll('_', ' ')).join(', ')}</span></div>
          <div className="policy-note"><b>Recommended option · {plan.recommendation.recommended.name}</b><span>{plan.recommendation.explanation}</span></div><div className="policy-note"><b>Recommended percentage change</b><span>{plan.recommendation.recommended.implementation.instruction}</span></div>
          <section className="policy-note"><b>Expected simulated profile</b><span>Resource access {(plan.recommendation.recommended.preview.resource_access * 100).toFixed(1)}% · stress {(plan.recommendation.recommended.preview.stress * 100).toFixed(1)}% · trust {(plan.recommendation.recommended.preview.trust * 100).toFixed(1)}% · compliance {(plan.recommendation.recommended.preview.compliance * 100).toFixed(1)}%.</span></section><button className="btn primary planner-run" onClick={apply}>REVIEW IN SIMULATOR →</button>
          <div className="policy-note"><b>Alternative options</b><span>{plan.recommendation.alternatives.map((item) => item.name).join(' · ')}</span></div><p className="helper">{plan.recommendation.boundary}</p>
        </>}
      </section>
    </div>
  </main>;
}
