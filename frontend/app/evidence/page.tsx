'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import EvidenceLegend from '@/components/EvidenceLegend';
import { api, ObservedMetric, SourceEntry } from '@/lib/api';

const domainLabels: Record<string, string> = {
  population: 'Population and households',
  water: 'Water',
  energy: 'Energy',
  housing: 'Housing',
  transport_bus: 'Bus transport',
  transport_metro: 'Metro transport',
};

function domain(metric: string) {
  if (metric.startsWith('water_')) return 'water';
  if (metric.includes('electricity')) return 'energy';
  if (metric.includes('building')) return 'housing';
  if (metric.startsWith('mtc_')) return 'transport_bus';
  if (metric.startsWith('cmrl_')) return 'transport_metro';
  return 'population';
}

function toCsv(rows: ObservedMetric[]) {
  const fields: Array<keyof ObservedMetric> = ['dataset', 'geography', 'period', 'metric', 'value', 'unit', 'source_org', 'source_url', 'evidence_type', 'notes'];
  const escape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  return [fields.join(','), ...rows.map((row) => fields.map((field) => escape(row[field])).join(','))].join('\n');
}

export default function EvidencePage() {
  const [metrics, setMetrics] = useState<ObservedMetric[]>([]);
  const [sources, setSources] = useState<SourceEntry[]>([]);
  const [activeDomain, setActiveDomain] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.chennaiObserved()
      .then((data) => { setMetrics(data.metrics); setSources(data.sources.sources || []); })
      .catch(() => setError('Could not load Chennai observed data. Is the API running?'));
  }, []);

  const sourceOrgs = useMemo(() => [...new Set(metrics.map((item) => item.source_org))].sort(), [metrics]);
  const filtered = useMemo(() => metrics.filter((item) => {
    if (activeDomain !== 'all' && domain(item.metric) !== activeDomain) return false;
    if (sourceFilter !== 'all' && item.source_org !== sourceFilter) return false;
    return !search || `${item.metric} ${item.source_org} ${item.period}`.toLowerCase().includes(search.toLowerCase());
  }), [metrics, activeDomain, sourceFilter, search]);
  const groups = useMemo(() => filtered.reduce<Record<string, ObservedMetric[]>>((all, item) => {
    const key = domain(item.metric);
    (all[key] ||= []).push(item);
    return all;
  }, {}), [filtered]);

  const metro = useMemo(() => metrics
    .filter((item) => item.metric === 'cmrl_annual_passengers')
    .sort((a, b) => a.period.localeCompare(b.period))
    .map((item) => ({ period: item.period, journeys: Number(item.value) })), [metrics]);

  const bus = useMemo(() => metrics
    .filter((item) => item.metric === 'mtc_fleet_strength' || item.metric === 'mtc_passengers_per_day')
    .reduce<Record<string, Record<string, number>>>((all, item) => {
      (all[item.period] ||= {})[item.metric] = Number(item.value);
      return all;
    }, {}), [metrics]);

  function exportCsv() {
    const blob = new Blob([toCsv(filtered)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'chennai_observed_metrics.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="page-shell">
      <div className="page-heading"><div><div className="label">Observed data</div><h1>Chennai evidence layer.</h1><p>Official aggregate context for calibration and scenario design. It is not an agent-level behavioural dataset.</p></div></div>
      <EvidenceLegend />
      <div className="policy-note"><b>Evidence boundary</b><span>Population and city-service records below are observed. Agent-level income, resource access, trust, stress, compliance and policy response remain synthetic unless a separate source is added.</span></div>
      {error && <div className="error-box mt-6">{error}</div>}
      {!error && !metrics.length && <div className="loading-card mt-6">Loading Chennai observations…</div>}
      {!!metrics.length && <>
        <div className="filter-row">
          {['all', ...Object.keys(domainLabels)].map((item) => <button className={`chip ${activeDomain === item ? 'active' : ''}`} key={item} onClick={() => setActiveDomain(item)}>{item === 'all' ? 'All domains' : domainLabels[item]}</button>)}
          <select className="input compact-input" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="all">All sources</option>{sourceOrgs.map((org) => <option key={org}>{org}</option>)}</select>
          <input className="input compact-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search metric, source or year" />
          <button className="btn" onClick={exportCsv}>Export CSV ({filtered.length})</button>
        </div>

        <div className="evidence-grid">{Object.entries(groups).map(([key, rows]) => <section className="card p-6" key={key}><div className="label">{domainLabels[key]}</div><div className="space-y-4 mt-5">{rows.map((item) => <article className="evidence-row" key={`${item.dataset}-${item.period}-${item.metric}`}><div className="evidence-value"><b>{item.metric.replaceAll('_', ' ')}</b><span>{Number(item.value).toLocaleString()} {item.unit.replaceAll('_', ' ')}</span></div><p className="helper">{item.geography} · {item.period}</p><a className="source-link" href={item.source_url} target="_blank" rel="noreferrer">Source: {item.source_org} ↗</a></article>)}</div></section>)}</div>

        {(metro.length > 0 || Object.keys(bus).length > 0) && <div className="analysis-grid evidence-charts">
          {metro.length > 0 && <section className="card p-6"><div className="label">Metro transport trend</div><h2 className="section-title">CMRL annual ridership</h2><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={metro}><CartesianGrid stroke="#16283c" strokeDasharray="3 3" /><XAxis dataKey="period" stroke="#71839a" /><YAxis stroke="#71839a" tickFormatter={(value) => `${(value / 1e6).toFixed(0)}M`} /><Tooltip contentStyle={{ background: '#0b1727', border: '1px solid #263e58', borderRadius: 10 }} formatter={(value: number) => value.toLocaleString()} /><Line type="monotone" dataKey="journeys" name="Passenger journeys" stroke="#52d3b4" strokeWidth={2.5} dot={{ r: 4 }} /></LineChart></ResponsiveContainer></div></section>}
          {Object.keys(bus).length > 0 && <section className="card p-6"><div className="label">Bus transport context</div><h2 className="section-title">MTC available indicators</h2><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={Object.entries(bus).map(([period, values]) => ({ period, fleet: values.mtc_fleet_strength, passengers: values.mtc_passengers_per_day }))}><CartesianGrid stroke="#16283c" strokeDasharray="3 3" /><XAxis dataKey="period" stroke="#71839a" /><YAxis stroke="#71839a" /><Tooltip contentStyle={{ background: '#0b1727', border: '1px solid #263e58', borderRadius: 10 }} /><Bar dataKey="fleet" name="Fleet (buses)" fill="#6fb1fb" radius={[6, 6, 0, 0]} /><Bar dataKey="passengers" name="Passengers/day (lakh)" fill="#f5a623" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></div><p className="helper">Reference periods vary; this is context, not a continuous time series.</p></section>}
        </div>}

        {!!sources.length && <section className="card p-6 source-catalog"><div className="label">Source status catalog</div><h2 className="section-title">What is incorporated</h2><p className="helper">Sources not normalized into metrics remain catalogued rather than estimated.</p><div className="source-grid">{sources.map((source) => <article className="source-card" key={source.name}><h3>{source.name}</h3><p>{source.publisher} · {source.years.join(', ')}</p><p>{source.integration_status.replaceAll('_', ' ')}</p><a className="source-link" href={source.url} target="_blank" rel="noreferrer">View source ↗</a></article>)}</div></section>}
      </>}
    </main>
  );
}
