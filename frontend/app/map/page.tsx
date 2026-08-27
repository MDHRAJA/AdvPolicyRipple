'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChennaiWards, WardProfile, api } from '@/lib/api';

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

export default function WardMapPage() {
  const [wards, setWards] = useState<ChennaiWards | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [profile, setProfile] = useState<WardProfile | null>(null);
  const [error, setError] = useState('');

  useEffect(() => { api.chennaiWards().then(setWards).catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load the official ward layer.')); }, []);
  useEffect(() => { if (!selected) return; setProfile(null); api.wardProfile(selected).then(setProfile).catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load this ward profile.')); }, [selected]);

  const projection = useMemo(() => {
    const positions = wards ? wards.features.flatMap((feature) => collectPositions(feature.geometry.coordinates)) : [];
    const longitudes = positions.map(([longitude]) => longitude); const latitudes = positions.map(([, latitude]) => latitude);
    const minX = Math.min(...longitudes); const maxX = Math.max(...longitudes); const minY = Math.min(...latitudes); const maxY = Math.max(...latitudes);
    return (position: Position) => [((position[0] - minX) / (maxX - minX || 1)) * 960 + 20, 620 - ((position[1] - minY) / (maxY - minY || 1)) * 590] as Position;
  }, [wards]);

  return <main className="page-shell">
    <div className="page-heading"><div><div className="label">Observed geography</div><h1>Chennai ward explorer.</h1><p>Browse official Greater Chennai Corporation ward boundaries and administrative profiles. This first release deliberately does not turn city-wide context or synthetic simulation measures into ward-level observations.</p></div></div>
    <div className="evidence-legend"><span className="tag observed">OBSERVED DATA · GCC GIS</span><span className="tag synthetic">NO SYNTHETIC WARD VALUES</span><span className="tag simulation">NO WARD SIMULATION YET</span></div>
    {error && <div className="error-box">{error}</div>}
    <div className="ward-layout">
      <section className="card ward-map-card">
        <div className="ward-map-title"><div><div className="label">Official 2025 ward layer</div><h2 className="section-title">Select a ward to inspect its profile</h2></div>{wards && <span>{wards.features.length} wards</span>}</div>
        {!wards ? <div className="loading-card">Loading official GCC boundaries…</div> : <svg className="ward-map" viewBox="0 0 1000 650" role="img" aria-label="Interactive Greater Chennai Corporation ward map">{wards.features.map((feature) => { const ward = String(feature.properties.ward ?? feature.properties.ward_id); const zone = Number(feature.properties.zone ?? 0); const color = ['#215f72', '#2e766f', '#805c35', '#614a88', '#784a5b'][zone % 5]; const d = rings(feature as Feature).map((ring) => ring.map((point, index) => { const [x, y] = projection(point); return (index ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1); }).join(' ') + ' Z').join(' '); return <path key={ward} d={d} fill={color} className={selected === ward ? 'ward-shape selected' : 'ward-shape'} onClick={() => setSelected(ward)}><title>{'Ward ' + ward + ' · Zone ' + String(feature.properties.zone ?? '—')}</title></path>; })}</svg>}
        <p className="helper">Boundary geometry and administrative attributes: Greater Chennai Corporation GIS FeatureServer. Click any ward.</p>
      </section>
      <aside className="card ward-profile">
        <div className="label">Ward profile</div>
        {!selected ? <div className="planner-empty"><span>⌖</span><h2>Select a ward.</h2><p>Its official administrative profile and provenance will appear here.</p></div> : !profile ? <div className="loading-card">{'Loading Ward ' + selected + '…'}</div> : <><h2 className="section-title">{'Ward ' + profile.ward}</h2><div className="profile-list"><div><span>Zone</span><b>{profile.zone || 'Not supplied'}</b></div><div><span>Region</span><b>{profile.region || 'Not supplied'}</b></div><div><span>Assembly constituency</span><b>{profile.assembly_constituency || 'Not supplied'}</b></div><div><span>Official boundary area</span><b>{profile.official_area_square_metres ? Number(profile.official_area_square_metres).toLocaleString() + ' m²' : 'Not supplied'}</b></div></div><div className="policy-note"><b>Observed scope</b><span>{profile.provenance}</span></div><div className="policy-note"><b>Data boundary</b><span>{profile.data_boundary}</span></div><a className="source-link" href={profile.source_url} target="_blank" rel="noreferrer">Open official GCC GIS source ↗</a></>}
      </aside>
    </div>
  </main>;
}
