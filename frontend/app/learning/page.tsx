const stages = [
  ['1. Establish context', 'Use the Chennai evidence layer to inspect the aggregate data available for calibration and scenario design.'],
  ['2. State assumptions', 'Choose the synthetic population preset, policy parameters, simulation horizon and random seed.'],
  ['3. Compare outcomes', 'Read model outputs alongside uncertainty ranges and rerun with different seeds or scenarios.'],
];

export default function Learning() {
  return (
    <main className="page-shell">
      <div className="page-heading"><div><div className="label">Learning & calibration</div><h1>Make the model auditable.</h1><p>PolicyForge separates what is observed from what is generated and what the simulation produces.</p></div></div>
      <div className="entry-grid">{stages.map(([title, body]) => <section className="card p-6" key={title}><div className="label">{title}</div><p className="helper learning-copy">{body}</p></section>)}</div>
      <section className="card p-7 home-note"><div><div className="label">Important limitation</div><h2>Calibration is not a real-world forecast.</h2></div><p>Observed Chennai aggregates anchor the context. Behavioural variables and the resulting policy effects remain explicit synthetic-model assumptions.</p></section>
    </main>
  );
}
