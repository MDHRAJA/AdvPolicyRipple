'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AIInterpreterStatus, AIPlannerSession, api, PolicyPlan, SimulationConfig } from '@/lib/api';

const objectives = [
  ['improve_access', 'Improve access'],
  ['reduce_stress', 'Reduce stress'],
  ['reduce_inequality', 'Reduce inequality'],
  ['build_trust', 'Build trust'],
  ['improve_compliance', 'Improve compliance'],
] as const;

function reviewedConfig(plan: PolicyPlan): SimulationConfig {
  const bundle = plan.recommendation?.recommended.policy_bundle || [];
  if (!bundle.length) return plan.proposed_config;
  return {
    ...plan.proposed_config,
    policy_id: bundle[0].policy_id,
    policy_parameters: bundle[0].policy_parameters,
    policy_bundle: bundle.length > 1
      ? bundle.map((item) => ({ policy_id: item.policy_id, policy_parameters: item.policy_parameters }))
      : [],
  };
}

function PlannerPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [prompt, setPrompt] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [interpreter, setInterpreter] = useState<AIInterpreterStatus | null>(null);

  useEffect(() => { api.aiStatus().then(setInterpreter).catch(() => setInterpreter(null)); }, []);
  useEffect(() => {
    const wards = searchParams.get('wards') || searchParams.get('ward');
    if (wards) setPrompt('Chennai Wards ' + wards + ': describe the local problem and propose a fair policy response.');
    else if (searchParams.get('allChennai')) setPrompt('Chennai citywide: describe the local problem and propose a fair policy response.');
  }, [searchParams]);

  function toggle(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  function saveAndOpen(config: SimulationConfig, result: Awaited<ReturnType<typeof api.runSession>>, aiPlanner: AIPlannerSession) {
    window.sessionStorage.setItem('policyforge:lastSimulation', JSON.stringify({ config, result, aiPlanner }));
    router.push('/results');
  }

  async function analyseAndSimulate() {
    const policyQuestion = prompt.trim();
    if (!policyQuestion) {
      setError('Describe the policy problem before running the AI Planner.');
      return;
    }

    setBusy(true);
    setError('');
    try {
      // The advice is saved with the result so the full proposal and evidence
      // appear together on one page. A simulation never waits for a second click.
      const advicePromise = api.policyAdvice({ prompt: policyQuestion, objectives: selected })
        .then((advice) => ({ advice }))
        .catch((reason) => ({ adviceError: reason instanceof Error ? reason.message : 'The AI policy brief was unavailable.' }));
      const triage = await api.triagePolicy(policyQuestion);

      if (triage.mode === 'simulation_ready') {
        const plan = await api.planPolicy({ prompt: policyQuestion, objectives: selected, size: 10000, rounds: 20, seed: 42 });
        const recommendation = await api.policyRecommendation(plan.proposed_config, plan.objectives);
        const completePlan = { ...plan, recommendation };
        const config = reviewedConfig(completePlan);
        // recommend() already simulated this exact winning configuration.
        // Reuse that outcome rather than performing an identical second run.
        const result = recommendation.recommended.result;
        const adviceState = await advicePromise;
        saveAndOpen(config, result, { prompt: policyQuestion, objectives: selected, triage, plan: completePlan, ...adviceState });
        return;
      }

      // A request without a supported preset is still shown in the same Results
      // page, but remains explicitly labelled as Gemini assumption-driven.
      const scenario = await api.exploratoryScenario({ prompt: policyQuestion, objectives: selected });
      const adviceState = await advicePromise;
      saveAndOpen(scenario.config, scenario.result, { prompt: policyQuestion, objectives: selected, triage, ...adviceState });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The AI Planner could not prepare this result.');
      setBusy(false);
    }
  }

  return <main className="page-shell planner-page">
    <div className="page-heading"><div><div className="label">AI-assisted policy planning</div><h1>Describe the problem in your own words.</h1><p>PolicyForge identifies the best available simulation route, runs it automatically, then opens one complete results page with the AI proposal and evidence.</p></div></div>
    <div className="planner-grid">
      <section className="card p-6">
        <div className="label">01 · Policy question</div>
        <textarea className="planner-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-label="Policy problem description" disabled={busy} />
        <div className="label planner-label">02 · What matters most?</div>
        <div className="objective-list">{objectives.map(([id, label]) => <button key={id} className={`chip ${selected.includes(id) ? 'active' : ''}`} onClick={() => toggle(id)} disabled={busy}>{label}</button>)}</div>
        <button className="btn primary planner-run" onClick={() => void analyseAndSimulate()} disabled={busy}>{busy ? 'ANALYSING & SIMULATING…' : 'ANALYSE POLICY & VIEW RESULTS →'}</button>
        {error && <div className="error-box">{error}</div>}
        <p className="helper"><b>Interpreter: {interpreter?.display || 'Checking backend…'}</b>{interpreter ? ` · ${interpreter.fallback}` : ''}</p>
      </section>
      <section className="card p-6 planner-result-route" aria-live="polite">
        {busy ? <div className="comparison-loader" role="status"><span className="comparison-loader-mark" aria-hidden="true" /><div><b>Preparing your complete policy result</b><span>PolicyForge is selecting the appropriate route, preparing the policy proposal, running the simulation, and opening Results automatically.</span></div></div> : <div className="planner-empty"><span>✦</span><h2>One request. One results page.</h2><p>Supported interventions are compared using the validated 10,000-agent simulator. Other policy ideas are shown as clearly labelled Gemini assumption-driven scenarios in the same results format.</p></div>}
      </section>
    </div>
  </main>;
}

export default function PlannerPage() {
  return <Suspense fallback={<main className="page-shell"><div className="loading-card">Loading AI policy planner…</div></main>}><PlannerPageContent /></Suspense>;
}
