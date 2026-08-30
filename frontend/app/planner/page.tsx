'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AIInterpreterStatus, api, PolicyAdvice, PolicyPlan, PolicyTriage } from '@/lib/api';

const objectives = [
  ['improve_access', 'Improve access'],
  ['reduce_stress', 'Reduce stress'],
  ['reduce_inequality', 'Reduce inequality'],
  ['build_trust', 'Build trust'],
  ['improve_compliance', 'Improve compliance'],
] as const;

function percentagePointChange(value: number) { return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} percentage points`; }

function PolicyAdviceBrief({ advice, error, onRetry }: { advice: PolicyAdvice | null; error?: string; onRetry?: () => void }) {
  if (error) return <div className="error-box"><b>Gemini policy agent is unavailable.</b><span>{error}</span>{onRetry ? <button className="btn secondary" onClick={onRetry}>TRY GEMINI AGAIN</button> : null}</div>;
  if (!advice) return <div className="policy-design-loading" role="status"><span className="comparison-loader-mark" aria-hidden="true" /><div><b>Drafting an AI policy proposal</b><span>PolicyForge is preparing a concrete Chennai policy design, not a simulation result.</span></div></div>;
  return <section className="policy-design-brief">
    <div className="label">AI policy recommendation · {advice.source === 'gemini' ? 'Gemini-assisted' : 'Local policy template'}</div>
    <h3>{advice.title}</h3>
    <p className="advice-executive">{advice.executive_recommendation}</p>
    <div className="advice-section"><b>Recommended policy design</b><p>{advice.policy_design}</p></div>
    <div className="advice-two-col"><div className="advice-section"><b>Who and where to target</b><p>{advice.targeting}</p></div><div className="advice-section"><b>Funding approach</b><p>{advice.budget_strategy}</p></div></div>
    <div className="advice-section"><b>Core policy actions</b>{advice.recommendations.map((item) => <div key={item.action} className="income-impact"><strong>{item.action}</strong> — {item.detail}<em>Why this is proposed: {item.rationale} Safeguard: {item.safeguard}</em></div>)}</div>
    <div className="advice-section"><b>Implementation sequence</b>{advice.implementation_plan.map((item) => <div key={item.phase} className="advice-phase"><strong>{item.phase}</strong><span>{item.timeframe} · {item.owner}</span><p>{item.action}</p></div>)}</div>
    <div className="advice-two-col"><div className="advice-section"><b>Success measures</b><ul>{advice.success_measures.map((item) => <li key={item}>{item}</li>)}</ul></div><div className="advice-section"><b>Trade-offs to manage</b><ul>{advice.key_tradeoffs.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
    <div className="advice-section"><b>Decisions needed before launch</b><ul>{advice.decisions_required.map((item) => <li key={item}>{item}</li>)}</ul></div>
    {advice.follow_up_questions.length ? <div className="advice-section"><b>What the AI needs to refine this proposal</b><ul>{advice.follow_up_questions.map((question) => <li key={question}>{question}</li>)}</ul><p>Update the policy question with those details, then interpret it again.</p></div> : null}
    <p className="helper">{advice.boundary}</p>{advice.fallback_note ? <p className="helper">{advice.fallback_note}</p> : null}
  </section>;
}

function PlannerPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [prompt, setPrompt] = useState('Water shortages are affecting low-income Chennai households. Explore a fair 25% response.');
  const [selected, setSelected] = useState<string[]>(['improve_access', 'reduce_stress', 'reduce_inequality']);
  const [plan, setPlan] = useState<PolicyPlan | null>(null);
  const [advice, setAdvice] = useState<PolicyAdvice | null>(null);
  const [adviceError, setAdviceError] = useState('');
  const [triage, setTriage] = useState<PolicyTriage | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [runningReviewedPolicy, setRunningReviewedPolicy] = useState(false);
  const [interpreter, setInterpreter] = useState<AIInterpreterStatus | null>(null);

  useEffect(() => { api.aiStatus().then(setInterpreter).catch(() => setInterpreter(null)); }, []);
  useEffect(() => { const wards = searchParams.get('wards') || searchParams.get('ward'); if (wards) setPrompt('Chennai Wards ' + wards + ': describe the local problem and propose a fair policy response.'); else if (searchParams.get('allChennai')) setPrompt('Chennai citywide: describe the local problem and propose a fair policy response.'); }, [searchParams]);

  function toggle(id: string) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]); }
  async function loadAdvice(policyQuestion: string) {
    setAdvice(null); setAdviceError('');
    try {
      setAdvice(await api.policyAdvice({ prompt: policyQuestion, objectives: selected }));
    } catch (reason) {
      setAdviceError(reason instanceof Error ? reason.message : 'The Gemini policy agent could not provide advice. Check the deployment settings and try again.');
    }
  }
  async function interpret(policyQuestion = prompt) {
    setBusy(true); setError(''); setPlan(null); setAdvice(null); setAdviceError(''); setTriage(null);
    try {
      const triageResult = await api.triagePolicy(policyQuestion);
      setTriage(triageResult);
      if (triageResult.mode !== 'simulation_ready') {
        void loadAdvice(policyQuestion);
        return;
      }
      const quickPlan = await api.planPolicy({ prompt: policyQuestion, objectives: selected, size: 10000, rounds: 20, seed: 42 });
      setPlan(quickPlan);
      void loadAdvice(policyQuestion);
      setAssessing(true);
      void api.policyRecommendation(quickPlan.proposed_config, quickPlan.objectives)
        .then((recommendation) => setPlan((current) => current ? { ...current, recommendation } : current))
        .catch((reason) => setError(`Policy interpreted, but the full comparison could not finish: ${reason instanceof Error ? reason.message : 'unknown error'}`))
        .finally(() => setAssessing(false));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not assess this policy request.'); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!plan?.recommendation) return;
    const recommendation = plan.recommendation.recommended.policy_bundle;
    const reviewedConfig = recommendation.length ? {
      ...plan.proposed_config,
      policy_id: recommendation[0].policy_id,
      policy_parameters: recommendation[0].policy_parameters,
      policy_bundle: recommendation.length > 1 ? recommendation.map((item) => ({ policy_id: item.policy_id, policy_parameters: item.policy_parameters })) : [],
    } : plan.proposed_config;

    setRunningReviewedPolicy(true);
    setError('');
    try {
      const result = await api.runSession(reviewedConfig);
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(
          'policyforge:lastSimulation',
          JSON.stringify({ config: reviewedConfig, result }),
        );
      }
      router.push('/results');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The reviewed policy experiment could not run.');
      setRunningReviewedPolicy(false);
    }
  }

  return <main className="page-shell planner-page">
    <div className="page-heading"><div><div className="label">AI-assisted policy planning</div><h1>Describe the problem in your own words.</h1><p>PolicyForge turns your description into a reviewable simulation proposal, then ranks existing policy options against the objectives you choose.</p></div></div>
    <div className="planner-grid">
      <section className="card p-6">
        <div className="label">01 · Policy question</div>
        <textarea className="planner-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-label="Policy problem description" />
        <div className="label planner-label">02 · What matters most?</div>
        <div className="objective-list">{objectives.map(([id, label]) => <button key={id} className={`chip ${selected.includes(id) ? 'active' : ''}`} onClick={() => toggle(id)}>{label}</button>)}</div>
        <button className="btn primary planner-run" onClick={() => interpret()} disabled={busy || assessing}>{busy ? 'INTERPRETING…' : assessing ? 'COMPARING OPTIONS…' : 'INTERPRET POLICY →'}</button>
        {error && <div className="error-box">{error}</div>}
        <p className="helper"><b>Interpreter: {interpreter?.display || 'Checking backend…'}</b>{interpreter ? ` · ${interpreter.fallback}` : ''}</p><p className="helper">Review every proposed setting before simulation.</p>
      </section>
      <section className="card p-6">
        <div className="label">02 · AI policy brief</div>
        {!plan ? triage ? <div className="planner-empty"><span>✦</span><h2>{triage.title}</h2><p>{triage.explanation}</p><div className="label planner-label">AI policy-design route</div><PolicyAdviceBrief advice={advice} error={adviceError} onRetry={() => void loadAdvice(prompt)} /><p className="helper">No preset policy or simulated result is shown until the request has a supported, explicit mechanism that can be reviewed.</p></div> : <div className="planner-empty"><span>✦</span><h2>Waiting for a policy question.</h2><p>Describe a local problem, choose priorities, and PolicyForge will decide whether it can create a simulation-ready proposal or needs a separate policy-design brief. To target a location, include a valid Chennai ward number—for example, “Chennai Ward 92”.</p></div> : <>
          <h2 className="section-title">{plan.matched_policy.name}</h2>
          <p className="helper">{plan.interpretation}</p><p className="helper">Interpretation source: {plan.interpretation_source === 'gemini' ? 'Gemini-assisted, validated against PolicyForge policy limits' : 'Local rule-based fallback'}. Simulation metrics are always generated by PolicyForge.</p>
          <div className="plan-summary"><div><span>Population basis</span><b>{plan.policy_detail.population_basis}</b></div>{plan.policy_detail.population_basis.includes('Chennai') ? <div><span>Ward target</span><b>{plan.proposed_config.target_wards?.length ? 'Wards ' + plan.proposed_config.target_wards.join(', ') : 'All Chennai wards'}</b></div> : null}</div><div className="policy-note"><b>Proposed policy · {plan.matched_policy.name}</b><span>{plan.matched_policy.description} Parameter: {plan.policy_detail.parameter.replaceAll('_', ' ')} at {plan.policy_detail.value_percent}%.</span></div><div className="policy-note"><b>Our primary concern</b><span>{plan.objectives.map((item) => item.replaceAll('_', ' ')).join(', ')}</span></div>{plan.fiscal_consideration ? <div className="policy-note"><b>Funding consideration</b><span>{plan.fiscal_consideration}</span></div> : null}<div className="label planner-label">AI policy proposal</div><PolicyAdviceBrief advice={advice} error={adviceError} onRetry={() => void loadAdvice(prompt)} />
          {!plan.recommendation ? <div className="comparison-loader" role="status" aria-live="polite"><span className="comparison-loader-mark" aria-hidden="true" /><div><b>Assessing policy options</b><span>Comparing individual policies and combinations. Your detailed recommendation will appear here shortly.</span></div></div> : <>
          <div className="policy-note"><b>Recommended option · {plan.recommendation.recommended.name}</b><span>{plan.recommendation.explanation}</span></div>
          <div className="policy-note"><b>{plan.recommendation.recommended.policy_bundle.length > 1 ? 'Recommended policy combination' : 'Recommended percentage change'}</b><span>{plan.recommendation.recommended.policy_bundle.map((item) => <span key={item.policy_id} className="income-impact"><strong>{item.name}</strong> — {item.instruction}</span>)}</span></div>
          <section className="policy-note"><b>How each income group is affected</b><span>{(['low', 'middle', 'high'] as const).map((group) => { const impact = plan.recommendation!.recommended.income_groups[group]; return <span key={group} className="income-impact"><strong>{group === 'low' ? 'Low' : group === 'middle' ? 'Middle' : 'High'} income:</strong> Access {percentagePointChange(impact.change.resource_access)}, stress {percentagePointChange(impact.change.stress)}, trust {percentagePointChange(impact.change.trust)}, compliance {percentagePointChange(impact.change.compliance)}.</span>; })}<em>These are simulated changes from each synthetic group’s starting point; lower stress is favourable.</em></span></section>
          <section className="policy-note"><b>Expected simulated profile</b><span>Resource access {(plan.recommendation.recommended.preview.resource_access * 100).toFixed(1)}% · stress {(plan.recommendation.recommended.preview.stress * 100).toFixed(1)}% · trust {(plan.recommendation.recommended.preview.trust * 100).toFixed(1)}% · compliance {(plan.recommendation.recommended.preview.compliance * 100).toFixed(1)}%.</span></section>
          <button className="btn primary planner-run" onClick={() => void apply()} disabled={runningReviewedPolicy}>{runningReviewedPolicy ? 'RUNNING AI POLICY EXPERIMENT…' : 'RUN AI POLICY EXPERIMENT →'}</button>
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
