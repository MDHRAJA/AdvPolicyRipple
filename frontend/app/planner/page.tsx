'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AIInterpreterStatus, api, PolicyPlan } from '@/lib/api';

const objectives = [
  ['improve_access', 'Improve access'],
  ['reduce_stress', 'Reduce stress'],
  ['reduce_inequality', 'Reduce inequality'],
  ['build_trust', 'Build trust'],
  ['improve_compliance', 'Improve compliance'],
] as const;

function percentagePointChange(value: number) { return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} percentage points`; }

function PlannerPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [prompt, setPrompt] = useState('Water shortages are affecting low-income Chennai households. Explore a fair 25% response.');
  const [selected, setSelected] = useState<string[]>(['improve_access', 'reduce_stress', 'reduce_inequality']);
  const [plan, setPlan] = useState<PolicyPlan | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [interpreter, setInterpreter] = useState<AIInterpreterStatus | null>(null);

  useEffect(() => { api.aiStatus().then(setInterpreter).catch(() => setInterpreter(null)); }, []);
  useEffect(() => { const wards = searchParams.get('wards') || searchParams.get('ward'); if (wards) setPrompt('Chennai Wards ' + wards + ': describe the local problem and propose a fair policy response.'); else if (searchParams.get('allChennai')) setPrompt('Chennai citywide: describe the local problem and propose a fair policy response.'); }, [searchParams]);

  function toggle(id: string) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  async function interpret() {
    setBusy(true); setError(''); setPlan(null);
    try {
      const quickPlan = await api.planPolicy({ prompt, objectives: selected, size: 10000, rounds: 20, seed: 42 });
      setPlan(quickPlan);
      setAssessing(true);
      void api.policyRecommendation(quickPlan.proposed_config, quickPlan.objectives)
        .then((recommendation) => setPlan((current) => current ? { ...current, recommendation } : current))
        .catch((reason) => setError(`Policy interpreted, but the full comparison could not finish: ${reason instanceof Error ? reason.message : 'unknown error'}`))
        .finally(() => setAssessing(false));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not interpret this policy request.'); }
    finally { setBusy(false); }
  }
  function apply() {
    if (!plan?.recommendation) return;
    const recommendation = plan.recommendation.recommended.policy_bundle;
    const reviewedConfig = recommendation.length ? {
      ...plan.proposed_config,
      policy_id: recommendation[0].policy_id,
      policy_parameters: recommendation[0].policy_parameters,
      policy_bundle: recommendation.length > 1 ? recommendation.map((item) => ({ policy_id: item.policy_id, policy_parameters: item.policy_parameters })) : [],
    } : plan.proposed_config;
    const config = encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(reviewedConfig)))));
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
        <button className="btn primary planner-run" onClick={interpret} disabled={busy || assessing}>{busy ? 'INTERPRETING…' : assessing ? 'COMPARING OPTIONS…' : 'INTERPRET POLICY →'}</button>
        {error && <div className="error-box">{error}</div>}
        <p className="helper"><b>Interpreter: {interpreter?.display || 'Checking backend…'}</b>{interpreter ? ` · ${interpreter.fallback}` : ''}</p><p className="helper">Review every proposed setting before simulation.</p>
      </section>
      <section className="card p-6">
        <div className="label">02 · AI policy brief</div>
        {!plan ? <div className="planner-empty"><span>✦</span><h2>Waiting for a policy question.</h2><p>Describe a local problem, choose priorities, and PolicyForge will create a simulation-ready proposal. To target a location, include a valid Chennai ward number—for example, “Chennai Ward 92”.</p></div> : <>
          <h2 className="section-title">{plan.matched_policy.name}</h2>
          <p className="helper">{plan.interpretation}</p><p className="helper">Interpretation source: {plan.interpretation_source === 'gemini' ? 'Gemini-assisted, validated against PolicyForge policy limits' : 'Local rule-based fallback'}. Simulation metrics are always generated by PolicyForge.</p>
          <div className="plan-summary"><div><span>Population basis</span><b>{plan.policy_detail.population_basis}</b></div>{plan.policy_detail.population_basis.includes('Chennai') ? <div><span>Ward target</span><b>{plan.proposed_config.target_wards?.length ? 'Wards ' + plan.proposed_config.target_wards.join(', ') : 'All Chennai wards'}</b></div> : null}</div><div className="policy-note"><b>Proposed policy · {plan.matched_policy.name}</b><span>{plan.matched_policy.description} Parameter: {plan.policy_detail.parameter.replaceAll('_', ' ')} at {plan.policy_detail.value_percent}%.</span></div><div className="policy-note"><b>Why this was selected</b><span>Objectives: {plan.objectives.map((item) => item.replaceAll('_', ' ')).join(', ')}</span></div>
          {!plan.recommendation ? <div className="policy-note"><b>Full policy comparison in progress</b><span>PolicyForge is now comparing every supported policy and two-policy combination with 10,000 agents each. You can review this interpreted proposal while the detailed recommendation is prepared.</span></div> : <>
          <div className="policy-note"><b>Recommended option · {plan.recommendation.recommended.name}</b><span>{plan.recommendation.explanation}</span></div>
          <div className="policy-note"><b>{plan.recommendation.recommended.policy_bundle.length > 1 ? 'Recommended policy combination' : 'Recommended percentage change'}</b><span>{plan.recommendation.recommended.policy_bundle.map((item) => <span key={item.policy_id} className="income-impact"><strong>{item.name}</strong> — {item.instruction}</span>)}</span></div>
          <section className="policy-note"><b>How each income group is affected</b><span>{(['low', 'middle', 'high'] as const).map((group) => { const impact = plan.recommendation!.recommended.income_groups[group]; return <span key={group} className="income-impact"><strong>{group === 'low' ? 'Low' : group === 'middle' ? 'Middle' : 'High'} income:</strong> Access {percentagePointChange(impact.change.resource_access)}, stress {percentagePointChange(impact.change.stress)}, trust {percentagePointChange(impact.change.trust)}, compliance {percentagePointChange(impact.change.compliance)}.</span>; })}<em>These are simulated changes from each synthetic group’s starting point; lower stress is favourable.</em></span></section>
          <section className="policy-note"><b>Expected simulated profile</b><span>Resource access {(plan.recommendation.recommended.preview.resource_access * 100).toFixed(1)}% · stress {(plan.recommendation.recommended.preview.stress * 100).toFixed(1)}% · trust {(plan.recommendation.recommended.preview.trust * 100).toFixed(1)}% · compliance {(plan.recommendation.recommended.preview.compliance * 100).toFixed(1)}%.</span></section>
          <button className="btn primary planner-run" onClick={apply}>REVIEW IN SIMULATOR →</button>
          <div className="policy-note"><b>Alternative options</b><span>{plan.recommendation.alternatives.map((item) => item.name).join(' · ')}</span></div>
          <p className="helper">{plan.recommendation.boundary}</p>
          </>}
        </>}
      </section>
    </div>
  </main>;
}


export default function PlannerPage() {
  return <Suspense fallback={<main className="page-shell"><div className="loading-card">Loading AI policy planner…</div></main>}><PlannerPageContent /></Suspense>;
}
