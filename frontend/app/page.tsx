import Link from 'next/link';
import EvidenceLegend from '@/components/EvidenceLegend';

const entryPoints = [
  { href: '/simulate', number: '01', title: 'Run an experiment', body: 'Set a policy shock, agent sample, seed and simulation horizon.' },
  { href: '/scenarios', number: '02', title: 'Start from a scenario', body: 'Use reproducible water, housing, transport and energy starters.' },
  { href: '/evidence', number: '03', title: 'Inspect Chennai data', body: 'Browse the observed aggregates and every linked official source.' },
];

export default function Home() {
  return (
    <main className="page-shell forge-home">
      <section className="forge-hero">
        <div>
          <div className="label">Chennai-calibrated policy simulation</div>
          <h1>Explore policy choices before they reach people.</h1>
          <p>PolicyForge combines observed Chennai context with transparent synthetic-agent simulations, helping teams compare possible trade-offs without claiming to forecast individuals.</p>
          <div className="hero-actions">
            <Link className="btn primary" href="/simulate">Open simulator →</Link>
            <Link className="btn" href="/evidence">Explore Chennai data</Link>
          </div>
          <EvidenceLegend />
        </div>
        <aside className="forge-snapshot card">
          <div className="label">Chennai calibration anchor</div>
          <strong>4.65M</strong>
          <span>observed Census 2011 population</span>
          <div className="snapshot-rule" />
          <p>Population totals and service context are observed. Individual behaviour remains synthetic.</p>
          <Link href="/about">Read the evidence boundary →</Link>
        </aside>
      </section>

      <section className="forge-stats" aria-label="PolicyForge at a glance">
        <div><b>10,000</b><span>maximum synthetic agents</span></div>
        <div><b>5</b><span>simulation outcome metrics</span></div>
        <div><b>4</b><span>policy scenario starters</span></div>
        <div><b>3</b><span>evidence types clearly labelled</span></div>
      </section>

      <section className="home-section">
        <div className="section-intro"><div><div className="label">Start here</div><h2>Turn a policy question into an experiment.</h2></div><p>Begin from a scenario or configure your own. Every simulation is seeded so the settings can be reproduced and compared.</p></div>
        <div className="entry-grid">{entryPoints.map((entry) => <Link className="entry-card card" href={entry.href} key={entry.href}><span>{entry.number}</span><h3>{entry.title}</h3><p>{entry.body}</p><b>Open →</b></Link>)}</div>
      </section>

      <section className="home-section home-note card">
        <div><div className="label">How to read results</div><h2>Compare patterns, not predictions.</h2></div>
        <p>PolicyForge shows model outputs under stated assumptions. Use its results to ask better questions, test sensitivities across seeds, and identify effects worth investigating with domain experts and additional evidence.</p>
      </section>
    </main>
  );
}
