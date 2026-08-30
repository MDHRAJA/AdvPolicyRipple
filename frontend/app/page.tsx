import Link from 'next/link';
import EvidenceLegend from '@/components/EvidenceLegend';

const entryPoints = [
  { href: '/planner', number: '01', title: 'Ask the AI planner', body: 'Describe a Chennai policy problem in plain language and review its proposed mechanism.' },
  { href: '/simulate', number: '02', title: 'Run an experiment', body: 'Set a policy change, target wards, seed and simulation horizon.' },
  { href: '/results', number: '03', title: 'Compare outcomes', body: 'Read baseline-versus-policy effects and paired seeded model ranges.' },
];

export default function Home() {
  return (
    <main className="page-shell forge-home">
      <section className="forge-hero">
        <div>
          <div className="label">Observed Chennai context · synthetic policy simulation</div>
          <h1>Make policy trade-offs easier to see.</h1>
          <p>PolicyForge turns a policy question into a transparent synthetic experiment, anchored in clearly labelled Chennai context and designed for review—not false certainty.</p>
          <div className="hero-actions">
            <Link className="btn primary" href="/planner">Ask the AI planner →</Link>
            <Link className="btn" href="/simulate">Open simulator</Link>
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
        <div><b>10,000</b><span>synthetic agents per experiment</span></div>
        <div><b>9</b><span>reported simulation metrics</span></div>
        <div><b>7</b><span>supported policy mechanisms</span></div>
        <div><b>3</b><span>evidence types clearly labelled</span></div>
      </section>

      <section className="home-section">
        <div className="section-intro"><div><div className="label">Start here</div><h2>Move from question to a reviewable result.</h2></div><p>Start with an AI policy question, an editable simulation, or a previous result. Every experiment is seeded, reviewable, and reproducible.</p></div>
        <div className="entry-grid">{entryPoints.map((entry) => <Link className="entry-card card" href={entry.href} key={entry.href}><span>{entry.number}</span><h3>{entry.title}</h3><p>{entry.body}</p><b>Open →</b></Link>)}</div>
      </section>

      <section className="home-section home-note card">
        <div><div className="label">How to read results</div><h2>Compare patterns, not predictions.</h2></div>
        <p>PolicyForge shows baseline-versus-policy changes under stated assumptions. Use the paired seeded ranges to identify robust model patterns, then test the decision with domain experts and additional evidence.</p>
      </section>

      <section className="home-section workflow-card card" aria-label="PolicyForge workflow">
        <div className="label">A simple workflow</div>
        <div className="workflow-steps"><div><b>1</b><strong>Frame the question</strong><span>Choose the policy concern and what matters most.</span></div><div><b>2</b><strong>Review the experiment</strong><span>Inspect the policy settings, assumptions and targeted wards.</span></div><div><b>3</b><strong>Compare the result</strong><span>Read baseline changes and seeded model ranges.</span></div></div>
      </section>
    </main>
  );
}
