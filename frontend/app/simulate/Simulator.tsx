'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, ChennaiAnchor, Policy, PolicySelection, Population, SimulationConfig, SimulationResult } from '@/lib/api';

const presets: Record<string, { label: string; description: string }> = {
  balanced: { label: 'Balanced City', description: 'A mixed synthetic population with moderate baseline inequality.' },
  unequal: { label: 'Unequal City', description: 'Higher baseline inequality and more uneven resource access.' },
  dense: { label: 'High-Density City', description: 'A dense synthetic city with stronger neighborhood interactions.' },
  chennai_census_2011: { label: 'Chennai — Census 2011 anchored sample', description: 'Synthetic agents are scaled to the observed 2011 Chennai population; behavioral fields remain synthetic.' },
};

const scenarioDefaults: Record<string, Partial<SimulationConfig>> = {
  water: { policy_id: 'water_rationing', policy_parameters: { reduction: 0.25 }, population: { preset: 'balanced', size: 10000, neighborhoods: 8 }, rounds: 20 },
  housing: { policy_id: 'rent_zoning', policy_parameters: { cost_change: -0.15 }, population: { preset: 'unequal', size: 10000, neighborhoods: 8 }, rounds: 20 },
  transport: { policy_id: 'transport_subsidy', policy_parameters: { subsidy: 0.15 }, population: { preset: 'dense', size: 10000, neighborhoods: 8 }, rounds: 20 },
  energy: { policy_id: 'energy_rationing', policy_parameters: { reduction: 0.2 }, population: { preset: 'dense', size: 10000, neighborhoods: 8 }, rounds: 20 },
};

const metricLabels: Record<string, string> = { resource_access: 'Resource access', inequality: 'Inequality', stress: 'Stress', satisfaction: 'Satisfaction', policy_support: 'Policy support', compliance: 'Compliance', trust: 'Trust', relocation: 'Relocation', cooperation: 'Cooperation' };

export default function Simulator() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [populations, setPopulations] = useState<Population[]>([]);
  const [policy, setPolicy] = useState('water_rationing');
  const [preset, setPreset] = useState('balanced');
  const [size, setSize] = useState(10000);
  const [rounds, setRounds] = useState(20);
  const [seed, setSeed] = useState(42);
  const [parameter, setParameter] = useState(0.25);
  const [bundle, setBundle] = useState<PolicySelection[]>([]);
  const [targetWards, setTargetWards] = useState<string[]>([]);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [simulationId, setSimulationId] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);
  const [error, setError] = useState('');
  const [chennaiAnchor, setChennaiAnchor] = useState<ChennaiAnchor | null>(null);

  useEffect(() => {
    Promise.all([api.policies(), api.populations()]).then(([p, pop]) => { setPolicies(p); setPopulations(pop); }).catch(() => setError('Could not load the simulation catalog. Is the API running?')).finally(() => setLoadingCatalogs(false));
  }, []);

  useEffect(() => {
    const token = searchParams.get('config');
    if (token) {
      try {
        const shared = JSON.parse(decodeURIComponent(escape(window.atob(token)))) as SimulationConfig;
        setPolicy(shared.policy_id); setPreset(shared.population.preset); setSize(shared.population.size); setRounds(shared.rounds); setSeed(shared.seed);
        const value = Object.values(shared.policy_parameters)[0]; if (typeof value === 'number') setParameter(value);
        if (shared.policy_bundle?.length) setBundle(shared.policy_bundle.filter((item) => item.policy_id !== shared.policy_id));
        if (shared.target_wards?.length) setTargetWards(shared.target_wards);
        return;
      } catch { setError('Could not read the AI policy configuration.'); }
    }
    const requestedWard = searchParams.get('ward');
    if (requestedWard) { setPreset('chennai_census_2011'); setTargetWards([requestedWard]); }
    const scenario = searchParams.get('scenario');
    const presetConfig = scenario ? scenarioDefaults[scenario] : undefined;
    if (!presetConfig) return;
    if (presetConfig.policy_id) setPolicy(presetConfig.policy_id);
    if (presetConfig.population) { setPreset(presetConfig.population.preset); setSize(presetConfig.population.size); }
    if (presetConfig.rounds) setRounds(presetConfig.rounds);
    const value = Object.values(presetConfig.policy_parameters || {})[0];
    if (typeof value === 'number') setParameter(value);
  }, [searchParams]);

  useEffect(() => {
    if (preset !== 'chennai_census_2011') { setChennaiAnchor(null); return; }
    api.chennaiCalibration(size).then(setChennaiAnchor).catch(() => setError('Could not load the Chennai observed-data anchor.'));
  }, [preset, size]);

  const selectedPolicy = useMemo(() => policies.find((p) => p.id === policy), [policies, policy]);
  const parameterName = selectedPolicy?.parameters ? Object.keys(selectedPolicy.parameters)[0] : 'parameter';
  const parameterIsCost = parameterName === 'cost_change';
  const parameterLabel = parameterName === 'reduction' ? 'Reduction' : parameterIsCost ? 'Cost change' : parameterName.replace('_', ' ');
  const parameterMin = parameterIsCost ? -0.5 : 0;
  const parameterMax = parameterIsCost ? 0.25 : 0.8;

  useEffect(() => {
    if (!selectedPolicy) return;
    const value = selectedPolicy.parameters?.[parameterName];
    if (typeof value === 'number') setParameter(value);
  }, [selectedPolicy, parameterName]);

  const policyBundle = bundle.length ? [{ policy_id: policy, policy_parameters: { [parameterName]: parameter } }, ...bundle] : [];
  const config: SimulationConfig = { population: { preset, size, neighborhoods: 8 }, policy_id: policy, policy_parameters: { [parameterName]: parameter }, policy_bundle: policyBundle, target_wards: targetWards, rounds, seed };
  function addPolicyToBundle(policyId: string) { const selected = policies.find((item) => item.id === policyId); if (!selected || policyId === policy || bundle.some((item) => item.policy_id === policyId)) return; setBundle((current) => [...current, { policy_id: policyId, policy_parameters: { ...selected.parameters } }].slice(0, 1)); }
  function updateBundleParameter(policyId: string, name: string, value: number) { setBundle((current) => current.map((item) => item.policy_id === policyId ? { ...item, policy_parameters: { [name]: value } } : item)); }

  async function runSimulation() {
    setBusy(true); setError('');
    try {
      const created = await api.create(config);
      setSimulationId(created.simulation_id);
      const output = await api.run(created.simulation_id);
      setResult(output);
      if (typeof window !== 'undefined') window.sessionStorage.setItem('policyforge:lastSimulationId', created.simulation_id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Simulation failed.'); }
    finally { setBusy(false); }
  }

  if (loadingCatalogs) return <main className="page-shell"><div className="loading-card">Loading simulation workspace…</div></main>;

  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">Simulation workspace</div><h1>Design a policy experiment.</h1><p>Change one policy, run a seeded synthetic society, and inspect the second-order effects.</p></div>{simulationId && <button className="btn" onClick={() => router.push(`/results?id=${simulationId}`)}>Open full results →</button>}</div>
    <div className="workspace-grid">
      <section className="card p-6">
        <div className="label">01 · Population</div><h2 className="section-title">Choose your agent sample</h2>
        <div className="space-y-4 mt-6">
          <label className="field"><span>Population preset</span><select className="input" value={preset} onChange={(e) => setPreset(e.target.value)}>{(populations.length ? populations : Object.entries(presets).map(([id, v]) => ({ id, name: v.label, synthetic: true }))).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <p className="helper">{presets[preset]?.description || 'Synthetic population preset. Select the Chennai option to use its observed Census 2011 population anchor.'}</p>
          {chennaiAnchor && <div className="policy-note"><b>OBSERVED DATA · Chennai Census 2011</b><span>{chennaiAnchor.observed_population.toLocaleString()} people observed; this {chennaiAnchor.synthetic_sample_size.toLocaleString()}-agent sample represents {Math.round(chennaiAnchor.people_per_synthetic_agent).toLocaleString()} people per agent.</span><span>Trust, stress, compliance and resource access remain synthetic assumptions.</span></div>}
          {preset === 'chennai_census_2011' && <div className="policy-note"><b>Ward targeting</b><span>{targetWards.length ? 'Policy effects will be directly applied to Ward ' + targetWards.join(', ') + '. Ward allocation is synthetic.' : 'No specific ward selected; policy applies across the synthetic Chennai sample.'}</span><button className="btn" onClick={() => router.push('/map')}>Choose a ward on the map →</button></div>}
          <label className="field"><span>Rounds <b>{rounds}</b></span><input className="range" type="range" min="1" max="100" value={rounds} onChange={(e) => setRounds(Number(e.target.value))}/></label>
        </div>
        <div className="label mt-8">02 · Policy shock</div><h2 className="section-title">What changes?</h2>
        <div className="space-y-4 mt-6">
          <label className="field"><span>Policy</span><select className="input" value={policy} onChange={(e) => setPolicy(e.target.value)}>{policies.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          {selectedPolicy && <div className="policy-note"><b>{selectedPolicy.name}</b><span>{selectedPolicy.description}</span></div>}
          <label className="field"><span>{parameterLabel} <b>{Math.round(parameter * 100)}%</b></span><input className="range" type="range" min={parameterMin} max={parameterMax} step="0.05" value={parameter} onChange={(e) => setParameter(Number(e.target.value))}/></label>
          <label className="field"><span>Combine with one additional policy</span><select className="input" value="" onChange={(e) => { addPolicyToBundle(e.target.value); e.currentTarget.value = ''; }}><option value="">No additional policy</option>{policies.filter((item) => item.id !== policy && !bundle.some((entry) => entry.policy_id === item.id)).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          {bundle.map((entry) => { const companion = policies.find((item) => item.id === entry.policy_id); const companionParameter = companion ? Object.keys(companion.parameters)[0] : 'parameter'; const value = entry.policy_parameters[companionParameter] ?? 0; return <div className="policy-note" key={entry.policy_id}><b>{companion?.name}</b><span>{companion?.description}</span><label className="field"><span>{companionParameter.replace('_', ' ')} <b>{Math.round(value * 100)}%</b></span><input className="range" type="range" min={companionParameter === 'cost_change' ? -0.5 : 0} max={companionParameter === 'cost_change' ? 0.25 : 0.8} step="0.05" value={value} onChange={(e) => updateBundleParameter(entry.policy_id, companionParameter, Number(e.target.value))}/></label><button className="btn" onClick={() => setBundle([])}>Remove companion</button></div>; })}
          <div className="two-col"><label className="field"><span>Seed</span><input className="input" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))}/></label><label className="field"><span>Neighborhoods</span><input className="input muted-input" type="number" value={8} disabled /></label></div>
          <button className="btn primary run-button" onClick={runSimulation} disabled={busy}>{busy ? 'SIMULATING…' : 'RUN POLICYFORGE EXPERIMENT →'}</button>
          {error && <div className="error-box">{error}</div>}
        </div>
      </section>
      <section className="card p-6 result-panel"><div className="label">03 · Live output</div>{!result ? <div className="empty-result"><div className="orbit">◌</div><h2>Your experiment is ready.</h2><p>Configure the scenario on the left, then run it to see resource access, inequality, stress, trust and compliance evolve over time.</p><div className="mini-list"><span>Seeded & reproducible</span><span>Bounded synthetic agents</span><span>Decision support, not a forecast</span></div></div> : <SimulationPreview result={result} />}</section>
    </div>
  </main>;
}

function SimulationPreview({ result }: { result: SimulationResult }) {
  const metrics = Object.entries(result.final) as Array<[keyof typeof result.final, number]>;
  return <div><div className="result-hero"><div><h2 className="section-title">What happened?</h2><p className="helper">{result.timeline.length} rounds · seeded simulation</p></div><div className="score"><span>Unintended consequence</span><b>{Number(result.unintended_consequence_score).toFixed(2)}</b></div></div><div className="metric-grid">{metrics.map(([key, value]) => <div className="metric" key={key}><span>{metricLabels[key]}</span><b>{`${(Number(value) * 100).toFixed(1)}%`}</b><div className="metric-bar"><i style={{ width: `${Math.max(0, Math.min(100, Number(value) * 100))}%` }} /></div></div>)}</div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={result.timeline}><XAxis dataKey="round" stroke="#71839a"/><YAxis domain={[0,1]} stroke="#71839a"/><Tooltip contentStyle={{ background:'#0b1727', border:'1px solid #263e58', borderRadius:10 }}/><Line type="monotone" dataKey="resource_access" stroke="#52d3b4" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="stress" stroke="#f59e0b" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="trust" stroke="#60a5fa" strokeWidth={2} dot={false}/></LineChart></ResponsiveContainer></div><div className="legend-row"><span><i className="dot teal"/>Resource access</span><span><i className="dot amber"/>Stress</span><span><i className="dot blue"/>Trust</span></div></div>;
}
