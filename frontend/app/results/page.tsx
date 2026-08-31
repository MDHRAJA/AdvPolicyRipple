'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AIPlannerSession, api, Metrics, PolicyAdvice, SimulationConfig, SimulationResult } from '@/lib/api';
import { exportPresentationReport } from '@/lib/presentationReport';

const labels: Record<keyof Metrics, string> = { resource_access: 'Resource access', inequality: 'Inequality', stress: 'Stress', satisfaction: 'Satisfaction', policy_support: 'Policy support', compliance: 'Compliance', trust: 'Trust', relocation: 'Relocation', cooperation: 'Cooperation' };

type Assessment = { expected_outcome: Metrics; best_case: Metrics; worst_case: Metrics; uncertainty: Metrics; policy_effect: { baseline: Metrics; policy: Metrics; change: Metrics; min_change: Metrics; max_change: Metrics; runs: number; range_label: string }; evidence_used: string; limitations: string[] };

export default function ResultsPage() {
  const router = useRouter();
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [assessmentError, setAssessmentError] = useState('');
  const [aiPlanner, setAiPlanner] = useState<AIPlannerSession | null>(null);
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    setBusy(true); setError('');
    try {
      const raw = window.sessionStorage.getItem('policyforge:lastSimulation');
      if (!raw) throw new Error('This session has no simulation result yet.');
      const saved = JSON.parse(raw) as { config: SimulationConfig; result: SimulationResult; aiPlanner?: AIPlannerSession };
      setConfig(saved.config); setResult(saved.result); setAiPlanner(saved.aiPlanner || null);
      if (saved.result.exploratory_assessment) {
        setAssessment(saved.result.exploratory_assessment);
        setBusy(false);
      } else {
        // The main experiment is ready. Render it immediately and calculate
        // the more expensive five-pair baseline assessment in the background.
        setBusy(false);
        void api.assessment(saved.config).then(setAssessment)
          .catch((e) => setAssessmentError(e instanceof Error ? e.message : 'Could not calculate the paired baseline assessment.'));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this session result.');
      setBusy(false);
    }
  }, []);

  if (busy) return <main className="page-shell"><div className="loading-card">Loading results…</div></main>;
  if (error || !result || !config) return <main className="page-shell"><div className="empty-result card p-8"><div className="label">Results</div><h1>{error || 'No simulation selected.'}</h1><p>Run a scenario first, then return here for the full analysis.</p><button className="btn primary" onClick={() => router.push('/simulate')}>Open simulator →</button></div></main>;

  const isExploratory = result.scenario_mode === 'AI_ASSUMPTION_DRIVEN';

  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">{isExploratory ? 'Census-informed synthetic scenario' : 'Results & assessment'}</div><h1>Understand the policy effects.</h1><p>{isExploratory ? 'This graph applies transparent model assumptions to a Chennai Census 2011 anchored synthetic baseline. It is not an observed-data prediction or forecast.' : 'Five paired seeded runs compare this policy with an equivalent no-policy baseline in the synthetic model.'}</p></div><div className="result-actions">{result.ward_impacts && <button className="btn" onClick={() => router.push('/map')}>View ward impacts →</button>}<button className="btn" disabled={!assessment} onClick={() => { if (!assessment) return; try { setExportError(''); exportPresentationReport({ config, result, assessment, aiPlanner }); } catch (reason) { setExportError(reason instanceof Error ? reason.message : 'Could not open the PDF export.'); } }}>{assessment ? 'Export presentation report (PDF)' : 'Preparing report…'}</button><button className="btn" onClick={() => router.push('/simulate')}>← New experiment</button></div></div>
    {aiPlanner ? <AIPlannerProposal session={aiPlanner} /> : null}
    {exportError ? <div className="error-box">{exportError}</div> : null}
        <section className="assessment-hero card"><div><div className="label">Policy assessment</div><h2>{result.unintended_consequence_score >= 65 ? 'High impact' : result.unintended_consequence_score >= 50 ? 'Moderate impact' : 'Lower impact'}</h2><p>{isExploratory ? 'This exploratory view shows the consequences of the AI assumptions listed below. Change the policy question or assumptions and the scenario can change.' : 'This synthetic assessment summarizes likely trade-offs under the selected assumptions. Review the trajectory graph and uncertainty range below.'}</p></div><div className="assessment-score"><span>Unintended consequence</span><b>{Number(result.unintended_consequence_score).toFixed(2)}</b></div></section><div className="assessment-grid"><section className="card p-6"><div className="label">Who is affected?</div><h2 className="section-title">Income-group effects</h2>{result.income_group_impacts ? <div className="income-results">{(['low', 'middle', 'high'] as const).map((group) => <IncomeImpactRow key={group} group={group} impact={result.income_group_impacts![group]} />)}</div> : <p className="helper">Income-group effects are available for new simulation runs.</p>}<p className="helper">Changes are measured from each synthetic group’s starting point. A negative stress change is favourable; these are not observed predictions about real people.</p></section><section className="card p-6"><div className="label">Key outcomes</div><h2 className="section-title">Change vs no-policy baseline</h2>{assessment ? <><div className="outcome-row"><span>Stress</span><b>{formatDelta(assessment.policy_effect.change.stress)}</b></div><div className="outcome-row"><span>Trust</span><b>{formatDelta(assessment.policy_effect.change.trust)}</b></div><div className="outcome-row"><span>Compliance</span><b>{formatDelta(assessment.policy_effect.change.compliance)}</b></div></> : <p className="helper">{assessmentError || 'Calculating the baseline comparison…'}</p>}<div className="policy-note"><b>⚠ Unintended consequences</b><span>Score is a synthetic-model summary, not a policy implementation verdict.</span></div></section></div><section className="card p-6 mb-6"><div className="result-hero"><div><div className="label">Experiment</div><h2 className="section-title">{isExploratory ? result.exploratory_scenario?.title || 'Exploratory Chennai scenario' : (config.policy_bundle?.length ? config.policy_bundle : [{ policy_id: config.policy_id }]).map((item) => (item.policy_id || 'no policy').replaceAll('_', ' ')).join(' + ')}</h2><p className="helper">{isExploratory ? 'Chennai Census 2011 anchored synthetic population · AI assumptions visible below' : `${config.population.preset} · ${config.population.size.toLocaleString()} agents · ${config.rounds} rounds · seed ${config.seed}`}</p></div><div className="score"><span>Unintended consequence</span><b>{Number(result.unintended_consequence_score).toFixed(2)}</b></div></div>{result.observed_data_anchor && <div className="policy-note result-anchor"><b>OBSERVED DATA ANCHOR · Chennai Census 2011</b><span>{result.observed_data_anchor.observed_population.toLocaleString()} observed people; individual agent behaviour remains synthetic.</span></div>}{isExploratory && result.exploratory_scenario ? <div className="policy-note"><b>MODEL ASSUMPTIONS · NOT OBSERVED EFFECTS</b><span>{result.exploratory_scenario.summary}</span><span>{result.exploratory_scenario.assumptions.map((assumption) => <span className="income-impact" key={assumption}>{assumption}</span>)}</span></div> : null}<div className="metric-grid">{(Object.keys(labels) as Array<keyof Metrics>).map((key) => <Metric key={key} label={labels[key]} value={result.final[key]} />)}</div></section>
    <section className="card p-6 mb-6">
      <div className="label">Baseline versus policy</div>
      <h2 className="section-title">What changed relative to no policy?</h2>
      <p className="helper">{isExploratory ? 'The comparison below contrasts the no-policy synthetic baseline with the Census-informed synthetic scenario. It is not a statistical confidence interval, observed effect, or forecast.' : 'Each paired run starts with the same synthetic population and seed. The range below is model variation across runs, not a statistical confidence interval or a forecast.'}</p>
      {assessment ? <><div className="baseline-policy-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={baselinePolicyRows(assessment.policy_effect)} margin={{ top: 12, right: 10, left: -15, bottom: 0 }}><XAxis dataKey="metric" stroke="#71839a" tickLine={false} axisLine={false}/><YAxis domain={[0, 100]} tickFormatter={(value) => value + '%'} stroke="#71839a" tickLine={false} axisLine={false}/><Tooltip formatter={(value) => typeof value === 'number' ? value.toFixed(1) + '%' : value} contentStyle={{ background: '#0b1727', border: '1px solid #263e58', borderRadius: 10 }}/><Legend /><Bar dataKey="baseline" name="No-policy baseline" fill="#50677f" radius={[5, 5, 0, 0]} /><Bar dataKey="policy" name="Policy outcome" fill="#52d3b4" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></div><div className="range-list baseline-policy-ranges">{(['resource_access', 'stress', 'trust', 'compliance'] as Array<keyof Metrics>).map((key) => <PolicyEffectRange key={key} metric={key} effect={assessment.policy_effect} />)}</div><p className="helper">{assessment.policy_effect.range_label}</p></> : <p className="helper">{assessmentError || 'Calculating paired baseline comparison…'}</p>}
    </section>
    <div className="analysis-grid">
      <section className="card p-6"><div className="label">Trajectory</div><h2 className="section-title">How outcomes evolved</h2><div className="large-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={result.timeline}><XAxis dataKey="round" stroke="#71839a"/><YAxis domain={[0, 1]} stroke="#71839a"/><Tooltip contentStyle={{ background: '#0b1727', border: '1px solid #263e58', borderRadius: 10 }}/><Line type="monotone" dataKey="resource_access" stroke="#52d3b4" strokeWidth={2.5} dot={false}/><Line type="monotone" dataKey="inequality" stroke="#c084fc" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="stress" stroke="#f59e0b" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="trust" stroke="#60a5fa" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div><div className="legend-row"><span>Resource</span><span>Inequality</span><span>Stress</span><span>Trust</span></div></section>
      <section className="card p-6"><div className="label">Uncertainty</div><h2 className="section-title">Expected range</h2>{assessment ? <div className="range-list">{(Object.keys(labels) as Array<keyof Metrics>).map((key) => <div className="range-row" key={key}><div><b>{labels[key]}</b><span>{(assessment.worst_case[key] * 100).toFixed(1)}% — {(assessment.best_case[key] * 100).toFixed(1)}%</span></div><strong>{`${(assessment.expected_outcome[key] * 100).toFixed(1)}%`}</strong><div className="range-track"><i style={{ left: `${assessment.worst_case[key] * 100}%`, width: `${assessment.uncertainty[key] * 100}%` }} /></div></div>)}</div> : <p className="helper">{assessmentError || 'Calculating uncertainty…'}</p>}</section>
    </div>
    <section className="card p-6 mt-6"><div className="label">Interpretation</div><h2 className="section-title">Decision-support notes</h2><div className="notes-grid"><div><h3>What this says</h3><p>The simulation shows how the selected policy interacts with a synthetic population over time. Higher inequality and stress are treated as adverse outcomes; resource access, trust and compliance are treated as beneficial outcomes.</p></div><div><h3>What this does not say</h3><p>This is not an empirical prediction of real people. The assessment is generated from five seeded simulation runs and inherits every assumption in the synthetic model.</p></div><div><h3>Evidence</h3><p>{assessment?.evidence_used || 'Synthetic simulation evidence.'}</p></div></div>{assessment && <ul className="limitations">{assessment.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}</section>
  </main>;
}


function AIPlannerProposal({ session }: { session: AIPlannerSession }) {
  const advice = session.advice;
  const plan = session.plan;
  return <section className="card p-6 mb-6 ai-planner-proposal">
    <div className="label">AI Planner proposal</div>
    <h2 className="section-title">{plan?.recommendation?.recommended.name || advice?.title || session.triage.title}</h2>
    <p className="helper"><b>Your policy question:</b> {session.prompt}</p>
    {plan ? <div className="policy-note"><b>Interpreted policy · {plan.matched_policy.name}</b><span>{plan.interpretation}</span>{plan.recommendation ? <span className="income-impact"><strong>Selected after comparison:</strong> {plan.recommendation.explanation}</span> : null}</div> : <div className="policy-note"><b>Simulation route</b><span>{session.triage.explanation} This results page therefore uses transparent model assumptions rather than relabelling the request as a preset policy.</span></div>}
    <BudgetConstraint session={session} advice={advice} />
    {advice ? <AIAdviceSummary advice={advice} /> : session.adviceError ? <p className="helper">The separate AI narrative could not be loaded: {session.adviceError}</p> : null}
  </section>;
}

function BudgetConstraint({ session, advice }: { session: AIPlannerSession; advice?: PolicyAdvice }) {
  const statedConstraint = session.plan?.fiscal_consideration;
  return <section className="budget-constraint">
    <div className="label">Budget & delivery constraint</div>
    <h3>{statedConstraint ? 'Funding requirement recognised' : 'Funding position to confirm'}</h3>
    <div className="budget-grid">
      <div><b>{statedConstraint ? 'Stated budget constraint' : 'No explicit budget constraint supplied'}</b><p>{statedConstraint || 'No budget cap, funding limit, fiscal-neutrality rule, or allocation source was entered in the policy question.'}</p></div>
      <div><b>AI funding approach</b><p>{advice?.budget_strategy || 'The AI funding approach will appear here once Gemini returns the detailed policy proposal.'}</p></div>
    </div>
    <p className="helper">Budget constraints shape the AI policy design and implementation route. They change numeric outputs only where a selected PolicyForge mechanism explicitly models that budget effect.</p>
  </section>;
}

function AIAdviceSummary({ advice }: { advice: PolicyAdvice }) {
  return <>
    <div className="policy-note"><b>AI recommendation</b><span>{advice.executive_recommendation}</span></div>
    <div className="advice-two-col">
      <div className="advice-section"><b>Policy design</b><p>{advice.policy_design}</p></div>
      <div className="advice-section"><b>Targeting</b><p>{advice.targeting}</p></div>
    </div>
    <div className="advice-section"><b>Recommended actions</b>{advice.recommendations.map((item) => <div key={item.action} className="income-impact"><strong>{item.action}</strong> — {item.detail}<em>Why: {item.rationale} Safeguard: {item.safeguard}</em></div>)}</div>
    <div className="advice-two-col">
      <div className="advice-section"><b>Implementation sequence</b>{advice.implementation_plan.map((item) => <div key={item.phase} className="advice-phase"><strong>{item.phase}</strong><span>{item.timeframe} · {item.owner}</span><p>{item.action}</p></div>)}</div>
      <div className="advice-section"><b>Success measures</b><ul>{advice.success_measures.map((item) => <li key={item}>{item}</li>)}</ul><b>Trade-offs to manage</b><ul>{advice.key_tradeoffs.map((item) => <li key={item}>{item}</li>)}</ul></div>
    </div>
    <p className="helper">{advice.boundary}</p>
  </>;
}

function baselinePolicyRows(effect: Assessment['policy_effect']) {
  return (['resource_access', 'stress', 'trust', 'compliance'] as Array<keyof Metrics>).map((key) => ({
    metric: labels[key],
    baseline: effect.baseline[key] * 100,
    policy: effect.policy[key] * 100,
  }));
}

function PolicyEffectRange({ metric, effect }: { metric: keyof Metrics; effect: Assessment['policy_effect'] }) {
  const change = effect.change[metric];
  const minimum = effect.min_change[metric];
  const maximum = effect.max_change[metric];
  return <div className="range-row"><div><b>{labels[metric]} change</b><span>{formatDelta(minimum)} to {formatDelta(maximum)} across {effect.runs} paired runs</span></div><strong>{formatDelta(change)}</strong><div className="range-track"><i style={{ left: `${Math.min(minimum, maximum) * 50 + 50}%`, width: `${Math.abs(maximum - minimum) * 50}%` }} /></div></div>;
}

function IncomeImpactRow({ group, impact }: { group: 'low' | 'middle' | 'high'; impact: NonNullable<SimulationResult['income_group_impacts']>['low'] }) {
  const title = group === 'low' ? 'Low income' : group === 'middle' ? 'Middle income' : 'High income';
  return <div className="income-impact-result"><b>{title}</b><span>Access {formatDelta(impact.change.resource_access)} · Stress {formatDelta(impact.change.stress)} · Trust {formatDelta(impact.change.trust)} · Compliance {formatDelta(impact.change.compliance)}</span></div>;
}

function formatDelta(value: number) { return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} pp`; }

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><b>{(Number(value) * 100).toFixed(1)}%</b><div className="metric-bar"><i style={{ width: `${Math.max(0, Math.min(100, Number(value) * 100))}%` }} /></div></div>; }
