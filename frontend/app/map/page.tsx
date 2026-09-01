'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChennaiWards, SimulationResult, WardProfile, api } from '@/lib/api';

type Position = [number, number];
type Feature = { properties: Record<string, unknown>; geometry: { type: string; coordinates: unknown } };

function collectPositions(value: unknown, output: Position[] = []): Position[] {
  if (!Array.isArray(value)) return output;
  if (typeof value[0] === 'number' && typeof value[1] === 'number') output.push([value[0], value[1]]);
  else value.forEach((item) => collectPositions(item, output));
  return output;
}

function rings(feature: Feature): Position[][] {
  const coordinates = feature.geometry.coordinates;
  if (feature.geometry.type === 'Polygon') return coordinates as Position[][];
  if (feature.geometry.type === 'MultiPolygon') return (coordinates as Position[][][]).flat();
  return [];
}

function impactColor(change: number) { return change > .05 ? '#52d3b4' : change > 0 ? '#2e766f' : change > -.05 ? '#805c35' : '#b6495f'; }

function formatImpact(value: number) { return (value >= 0 ? '+' : '') + (value * 100).toFixed(1) + ' pp'; }

function WardMapPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [wards, setWards] = useState<ChennaiWards | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [targetWards, setTargetWards] = useState<string[]>([]);
  const [profile, setProfile] = useState<WardProfile | null>(null);
  const [wardQuery, setWardQuery] = useState('');
  const [searchMessage, setSearchMessage] = useState('');
  const [error, setError] = useState('');

  function toggleTargetWard(ward: string) {
    const wasTargeted = targetWards.includes(ward);
    setSelected(wasTargeted ? null : ward);
    setTargetWards((current) => wasTargeted ? current.filter((item) => item !== ward) : [...current, ward].sort((first, second) => Number(first) - Number(second)));
  }

  function selectSearchedWard() {
    const normalized = wardQuery.trim().replace(/^ward\s*/i, '');
    if (!normalized || !wards) return;
    const match = wards.features.find((feature) => String(feature.properties.ward ?? feature.properties.ward_id ?? '') === normalized);
    if (!match) {
      setSearchMessage('No Chennai ward matched that number. Enter a ward number from 1 to 200.');
      return;
    }
    const ward = String(match.properties.ward ?? match.properties.ward_id);
    setSelected(ward);
    setTargetWards((current) => current.includes(ward) ? current : [...current, ward].sort((first, second) => Number(first) - Number(second)));
    setWardQuery('Ward ' + ward);
    setSearchMessage('Ward ' + ward + ' is selected and added to the simulation target.');
  }

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem('policyforge:lastSimulation');
      if (raw) setSimulation((JSON.parse(raw) as { result: SimulationResult }).result);
    } catch { setError('Could not load the ward simulation overlay from this browser session.'); }
    const wards = searchParams.get('wards');
    if (wards) setTargetWards(wards.split(',').filter((ward) => /^\d{1,3}$/.test(ward)));
  }, [searchParams]);
  useEffect(() => { api.chennaiWards().then(setWards).catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load the official ward layer.')); }, []);
  useEffect(() => { if (!selected) return; setProfile(null); api.wardProfile(selected).then(setProfile).catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load this ward profile.')); }, [selected]);

  const projection = useMemo(() => {
    const positions = wards ? wards.features.flatMap((feature) => collectPositions(feature.geometry.coordinates)) : [];
    const longitudes = positions.map(([longitude]) => longitude); const latitudes = positions.map(([, latitude]) => latitude);
    const minX = Math.min(...longitudes); const maxX = Math.max(...longitudes); const minY = Math.min(...latitudes); const maxY = Math.max(...latitudes);
    return (position: Position) => [((position[0] - minX) / (maxX - minX || 1)) * 960 + 20, 620 - ((position[1] - minY) / (maxY - minY || 1)) * 590] as Position;
  }, [wards]);

  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">Observed geography</div><h1>Chennai Ward Explorer.</h1><p>Browse official Greater Chennai Corporation ward boundaries and administrative profiles. This first release deliberately does not turn city-wide context or synthetic simulation measures into ward-level observations.</p></div></div>
    <div className="evidence-legend"><span className="tag observed">OBSERVED DATA · GCC GIS</span><span className="tag synthetic">SYNTHETIC WARD ALLOCATION</span><span className="tag simulation">{simulation?.ward_impacts ? 'SIMULATION OUTPUT · ACCESS CHANGE' : 'NO WARD SIMULATION SELECTED'}</span></div>
    <section className="card map-target-bar"><div><div className="label">Simulation target</div><b>{targetWards.length ? 'Wards ' + targetWards.join(', ') : 'All Chennai wards'}</b><p>{targetWards.length ? 'Click more wards to add or remove them from this target.' : 'No specific wards selected: policy will apply citywide.'}</p></div><div className="map-target-actions"><button className="btn" onClick={() => setTargetWards([])}>Select all Chennai</button><button className="btn primary" onClick={() => router.push('/simulate?wards=' + targetWards.join(',') + (targetWards.length ? '' : '&allChennai=1'))}>Use in Simulator →</button><button className="btn" onClick={() => router.push('/planner?wards=' + targetWards.join(',') + (targetWards.length ? '' : '&allChennai=1'))}>Ask AI →</button></div></section>
    {error && <div className="error-box">{error}</div>}
    <div className="ward-layout">
      <section className="card ward-map-card">
        <div className="ward-map-title"><div><div className="label">Official 2025 ward layer</div><h2 className="section-title">Select a ward to inspect its profile</h2></div>{wards && <span>{wards.features.length} wards</span>}</div>
        <form className="ward-search" onSubmit={(event) => { event.preventDefault(); selectSearchedWard(); }}>
          <label htmlFor="ward-search">Find a ward by number</label>
          <div><input id="ward-search" className="input" list="ward-options" value={wardQuery} onChange={(event) => { setWardQuery(event.target.value); setSearchMessage(''); }} placeholder="Enter a ward number, e.g. 92" /><button className="btn" type="submit" disabled={!wards || !wardQuery.trim()}>Find & select</button></div>
          <datalist id="ward-options">{wards?.features.map((feature) => { const ward = String(feature.properties.ward ?? feature.properties.ward_id); return <option key={ward} value={'Ward ' + ward} />; })}</datalist>
          {searchMessage ? <span>{searchMessage}</span> : null}
        </form>
        {!wards ? <div className="loading-card">Loading official GCC boundaries…</div> : <svg className="ward-map" viewBox="0 0 1000 650" role="img" aria-label="Interactive Greater Chennai Corporation ward map">{wards.features.map((feature) => { const ward = String(feature.properties.ward ?? feature.properties.ward_id); const zone = Number(feature.properties.zone ?? 0); const impact = simulation?.ward_impacts?.[ward]; const color = impact ? impactColor(impact.change.resource_access) : ['#215f72', '#2e766f', '#805c35', '#614a88', '#784a5b'][zone % 5]; const d = rings(feature as Feature).map((ring) => ring.map((point, index) => { const [x, y] = projection(point); return (index ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1); }).join(' ') + ' Z').join(' '); return <path key={ward} d={d} fill={color} className={selected === ward ? 'ward-shape selected' : targetWards.includes(ward) ? 'ward-shape targeted' : 'ward-shape'} onClick={() => toggleTargetWard(ward)}><title>{'Ward ' + ward + ' · Zone ' + String(feature.properties.zone ?? '—')}</title></path>; })}</svg>}
        <p className="helper">Boundary geometry and administrative attributes: Greater Chennai Corporation GIS FeatureServer. Click any ward.</p>
      </section>
      <aside className="card ward-profile">
        <div className="label">Ward profile</div>
        {!selected ? <div className="planner-empty"><span>⌖</span><h2>Select a ward.</h2><p>Its official administrative profile and provenance will appear here.</p></div> : !profile ? <div className="loading-card">{'Loading Ward ' + selected + '…'}</div> : <><h2 className="section-title">{'Ward ' + profile.ward}</h2><div className="profile-list"><div><span>Zone</span><b>{profile.zone || 'Not supplied'}</b></div><div><span>Region</span><b>{profile.region || 'Not supplied'}</b></div><div><span>Assembly constituency</span><b>{profile.assembly_constituency || 'Not supplied'}</b></div><div><span>Official boundary area</span><b>{profile.official_area_square_metres ? Number(profile.official_area_square_metres).toLocaleString() + ' m²' : 'Not supplied'}</b></div></div><div className="policy-note"><b>Observed scope</b><span>{profile.provenance}</span></div><div className="policy-note"><b>Data boundary</b><span>{profile.data_boundary}</span></div><a className="source-link" href={profile.source_url} target="_blank" rel="noreferrer">Open official GCC GIS source ↗</a>{simulation?.ward_impacts?.[profile.ward] && <div className="policy-note"><b>SIMULATION OUTPUT · Ward effect</b><span>Access {formatImpact(simulation.ward_impacts[profile.ward].change.resource_access)} · stress {formatImpact(simulation.ward_impacts[profile.ward].change.stress)} · trust {formatImpact(simulation.ward_impacts[profile.ward].change.trust)}.</span><span>These effects use synthetic agent-to-ward allocation, not observed ward outcomes.</span></div>}<div className="policy-note"><b>Map selection</b><span>{targetWards.length ? 'Wards ' + targetWards.join(', ') + ' are selected for targeting.' : 'All Chennai wards are selected for citywide targeting.'}</span></div></>}
      </aside>
    </div>
  </main>;
}


export default function WardMapPage() {
  return <Suspense fallback={<main className="page-shell"><div className="loading-card">Loading Chennai ward explorer…</div></main>}><WardMapPageContent /></Suspense>;
}
