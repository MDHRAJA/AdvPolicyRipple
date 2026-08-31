import { AIPlannerSession, Metrics, SimulationConfig, SimulationResult } from '@/lib/api';

export type PresentationAssessment = {
  expected_outcome: Metrics;
  best_case: Metrics;
  worst_case: Metrics;
  uncertainty: Metrics;
  policy_effect: {
    baseline: Metrics;
    policy: Metrics;
    change: Metrics;
    min_change: Metrics;
    max_change: Metrics;
    runs: number;
    range_label: string;
  };
  evidence_used: string;
  limitations: string[];
};

type ReportInput = {
  config: SimulationConfig;
  result: SimulationResult;
  assessment: PresentationAssessment;
  aiPlanner: AIPlannerSession | null;
};

const keyMetrics: Array<keyof Metrics> = ['resource_access', 'stress', 'trust', 'compliance'];
const metricNames: Record<keyof Metrics, string> = {
  resource_access: 'Resource access',
  inequality: 'Inequality',
  stress: 'Stress',
  satisfaction: 'Satisfaction',
  policy_support: 'Policy support',
  compliance: 'Compliance',
  trust: 'Trust',
  relocation: 'Relocation',
  cooperation: 'Cooperation',
};

function escapeHtml(value: unknown) {
  const entities: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  };
  return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character] || character);
}

function percent(value: number) { return (Number(value) * 100).toFixed(1) + '%'; }
function delta(value: number) { return (value >= 0 ? '+' : '') + (value * 100).toFixed(1) + ' pp'; }

function policyTitle(config: SimulationConfig, result: SimulationResult) {
  if (result.scenario_mode === 'AI_ASSUMPTION_DRIVEN') return result.exploratory_scenario?.title || 'Exploratory Chennai policy scenario';
  const policies = config.policy_bundle?.length ? config.policy_bundle : [{ policy_id: config.policy_id }];
  return policies.map((item) => String(item.policy_id || 'no policy').replaceAll('_', ' ')).join(' + ');
}

function barChart(effect: PresentationAssessment['policy_effect']) {
  const width = 720;
  const height = 260;
  const baselineColor = '#71839a';
  const policyColor = '#52d3b4';
  const groupWidth = 160;
  const barWidth = 42;
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="No-policy baseline versus policy outcome chart">
    <line x1="40" y1="215" x2="700" y2="215" stroke="#c9d7e5" stroke-width="1"/>
    <line x1="40" y1="25" x2="40" y2="215" stroke="#c9d7e5" stroke-width="1"/>
    ${keyMetrics.map((metric, index) => {
      const baseline = effect.baseline[metric] * 170;
      const policy = effect.policy[metric] * 170;
      const x = 68 + index * groupWidth;
      return `<g>
        <rect x="${x}" y="${215 - baseline}" width="${barWidth}" height="${baseline}" rx="4" fill="${baselineColor}"/>
        <rect x="${x + 52}" y="${215 - policy}" width="${barWidth}" height="${policy}" rx="4" fill="${policyColor}"/>
        <text x="${x + 47}" y="238" text-anchor="middle" font-size="12" fill="#243548">${escapeHtml(metricNames[metric])}</text>
      </g>`;
    }).join('')}
    <rect x="462" y="12" width="12" height="12" fill="${baselineColor}"/><text x="480" y="22" font-size="12" fill="#243548">No-policy baseline</text>
    <rect x="602" y="12" width="12" height="12" fill="${policyColor}"/><text x="620" y="22" font-size="12" fill="#243548">Policy outcome</text>
  </svg>`;
}

function trajectoryChart(timeline: SimulationResult['timeline']) {
  const metrics: Array<{ key: keyof Metrics; color: string }> = [
    { key: 'resource_access', color: '#158c78' },
    { key: 'stress', color: '#cc7a00' },
    { key: 'trust', color: '#276fbc' },
    { key: 'inequality', color: '#805ad5' },
  ];
  const width = 720;
  const height = 260;
  const points = (key: keyof Metrics) => timeline.map((row, index) => {
    const x = 42 + (index / Math.max(1, timeline.length - 1)) * 650;
    const y = 215 - row[key] * 170;
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Outcome trajectory chart">
    <line x1="40" y1="215" x2="700" y2="215" stroke="#c9d7e5" stroke-width="1"/>
    <line x1="40" y1="25" x2="40" y2="215" stroke="#c9d7e5" stroke-width="1"/>
    ${metrics.map((item) => `<path d="${points(item.key)}" fill="none" stroke="${item.color}" stroke-width="3"/>`).join('')}
    ${metrics.map((item, index) => `<line x1="${45 + index * 165}" y1="242" x2="${61 + index * 165}" y2="242" stroke="${item.color}" stroke-width="3"/><text x="${67 + index * 165}" y="246" font-size="12" fill="#243548">${escapeHtml(metricNames[item.key])}</text>`).join('')}
  </svg>`;
}

function incomeRows(result: SimulationResult) {
  const impacts = result.income_group_impacts;
  if (!impacts) return '<p class="muted">Income-group effects were not included in this session.</p>';
  return ['low', 'middle', 'high'].map((group) => {
    const impact = impacts[group as 'low' | 'middle' | 'high'];
    return `<tr><td>${group[0].toUpperCase() + group.slice(1)} income</td><td>${delta(impact.change.resource_access)}</td><td>${delta(impact.change.stress)}</td><td>${delta(impact.change.trust)}</td><td>${delta(impact.change.compliance)}</td></tr>`;
  }).join('');
}

function adviceSection(aiPlanner: AIPlannerSession | null) {
  if (!aiPlanner) return '';
  const advice = aiPlanner.advice;
  const plan = aiPlanner.plan;
  const actions = advice?.recommendations.map((item) => `<li><strong>${escapeHtml(item.action)}</strong> - ${escapeHtml(item.detail)}<br/><em>Why: ${escapeHtml(item.rationale)} Safeguard: ${escapeHtml(item.safeguard)}</em></li>`).join('') || '';
  return `<section>
    <div class="eyebrow">AI POLICY PROPOSAL</div>
    <h2>${escapeHtml(plan?.recommendation?.recommended.name || advice?.title || aiPlanner.triage.title)}</h2>
    <p><strong>Policy question:</strong> ${escapeHtml(aiPlanner.prompt)}</p>
    ${plan ? `<div class="callout"><strong>Interpreted policy: ${escapeHtml(plan.matched_policy.name)}</strong><br/>${escapeHtml(plan.interpretation)}</div>` : `<div class="callout"><strong>Scenario route</strong><br/>${escapeHtml(aiPlanner.triage.explanation)}</div>`}
    ${advice ? `<p class="lead">${escapeHtml(advice.executive_recommendation)}</p>
      <div class="budget-callout"><strong>Budget constraint and funding route</strong><br/>${escapeHtml(plan?.fiscal_consideration || 'No explicit budget cap, funding limit, fiscal-neutrality rule, or allocation source was supplied in the policy question.')}<p><strong>AI funding approach:</strong> ${escapeHtml(advice.budget_strategy)}</p><p class="muted">Budget constraints guide policy design. They are not a numerical simulation input unless the selected PolicyForge mechanism explicitly models that effect.</p></div><div class="two-column"><div><h3>Policy design</h3><p>${escapeHtml(advice.policy_design)}</p></div><div><h3>Targeting</h3><p>${escapeHtml(advice.targeting)}</p></div></div>
      <h3>Recommended actions</h3><ol class="actions">${actions}</ol>
      <div class="two-column"><div><h3>Implementation sequence</h3>${advice.implementation_plan.map((item) => `<p><strong>${escapeHtml(item.phase)}</strong><br/><span class="muted">${escapeHtml(item.timeframe)} - ${escapeHtml(item.owner)}</span><br/>${escapeHtml(item.action)}</p>`).join('')}</div><div><h3>Trade-offs to manage</h3><ul>${advice.key_tradeoffs.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul><h3>Success measures</h3><ul>${advice.success_measures.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div></div>
      <p class="muted">${escapeHtml(advice.boundary)}</p>` : aiPlanner.adviceError ? `<p class="muted">The detailed AI narrative was unavailable: ${escapeHtml(aiPlanner.adviceError)}</p>` : ''}
  </section>`;
}

export function exportPresentationReport(input: ReportInput) {
  const { config, result, assessment, aiPlanner } = input;
  const isExploratory = result.scenario_mode === 'AI_ASSUMPTION_DRIVEN';
  const exportWindow = window.open('', '_blank');
  if (!exportWindow) throw new Error('Your browser blocked the report window. Allow pop-ups and try again.');

  const assumptions: string[] = isExploratory
    ? result.exploratory_scenario?.assumptions || []
    : Array.isArray(result.assumptions) ? result.assumptions.map(String) : [];
  const report = `<!doctype html>
  <html><head><meta charset="utf-8"/><title>PolicyForge presentation report</title>
  <style>
    @page { size: A4; margin: 15mm; }
    * { box-sizing: border-box; } body { color: #122235; font-family: Arial, Helvetica, sans-serif; font-size: 11px; line-height: 1.5; margin: 0; }
    h1 { font-size: 31px; line-height: 1; margin: 0 0 9px; letter-spacing: -1px; } h2 { font-size: 19px; margin: 0 0 8px; } h3 { font-size: 12px; margin: 14px 0 5px; } p { margin: 5px 0; } ul, ol { margin: 5px 0; padding-left: 18px; }
    section { border-top: 1px solid #c8d6e4; padding-top: 16px; margin-top: 18px; break-inside: avoid; } .hero { background: #092039; color: #eff8ff; padding: 24px; border-radius: 12px; } .hero p { color: #c1d5e7; max-width: 640px; }
    .brand { color: #37bda3; font-weight: 800; letter-spacing: 1px; font-size: 12px; } .eyebrow { color: #267c6d; font-size: 10px; font-weight: 700; letter-spacing: 1.1px; margin-bottom: 6px; }
    .meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 16px; } .meta div, .callout { background: #edf4f8; border: 1px solid #d4e1ea; border-radius: 7px; padding: 9px; } .meta span { display:block; color:#607286; font-size:9px; text-transform:uppercase; letter-spacing:.5px; } .meta b { display:block; margin-top:3px; font-size:12px; }
    .two-column { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; } .budget-callout { background:#e5f7f0; border:1px solid #9bdac9; border-left:4px solid #1e8e75; border-radius:7px; padding:10px; margin:12px 0; } .budget-callout p { margin-top:7px; } .callout { border-left: 4px solid #37bda3; margin: 10px 0; } .lead { font-size: 13px; line-height: 1.55; } .muted { color: #607286; } .actions li { margin-bottom: 8px; } em { color: #52677d; }
    table { width:100%; border-collapse: collapse; margin-top: 9px; } th { background:#092039; color:#fff; font-size:10px; text-align:left; } td, th { border:1px solid #cddae4; padding:7px; } td:not(:first-child), th:not(:first-child) { text-align:right; } .chart { width:100%; height:auto; display:block; margin-top:8px; } .footer { margin-top:24px; padding-top:10px; border-top:1px solid #c8d6e4; color:#607286; font-size:9px; } .page-break { break-before: page; }
  </style></head><body>
    <header class="hero"><div class="brand">POLICYFORGE</div><h1>Policy presentation report</h1><p>${isExploratory ? 'Census-informed synthetic Chennai scenario - Census-informed synthetic effects, not an observed forecast.' : 'Synthetic policy simulation - decision support, not a prediction of real people.'}</p>
      <div class="meta"><div><span>Experiment</span><b>${escapeHtml(policyTitle(config, result))}</b></div><div><span>Population</span><b>${config.population.size.toLocaleString()} synthetic agents</b></div><div><span>Generated</span><b>${new Date().toLocaleString()}</b></div></div>
    </header>
    ${adviceSection(aiPlanner)}
    <section><div class="eyebrow">OUTCOME SUMMARY</div><h2>Baseline versus policy</h2><p class="muted">${escapeHtml(assessment.policy_effect.range_label)}</p>${barChart(assessment.policy_effect)}
      <table><thead><tr><th>Metric</th><th>No-policy baseline</th><th>Policy outcome</th><th>Change</th></tr></thead><tbody>${keyMetrics.map((metric) => `<tr><td>${metricNames[metric]}</td><td>${percent(assessment.policy_effect.baseline[metric])}</td><td>${percent(assessment.policy_effect.policy[metric])}</td><td>${delta(assessment.policy_effect.change[metric])}</td></tr>`).join('')}</tbody></table>
    </section>
    <section><div class="eyebrow">DISTRIBUTIONAL EFFECTS</div><h2>Income-group impacts</h2><p class="muted">Changes are relative to each synthetic group’s starting point. Negative stress change is favourable.</p><table><thead><tr><th>Group</th><th>Access</th><th>Stress</th><th>Trust</th><th>Compliance</th></tr></thead><tbody>${incomeRows(result)}</tbody></table></section>
    <section><div class="eyebrow">SIMULATION TRAJECTORY</div><h2>How key outcomes evolved</h2>${trajectoryChart(result.timeline)}</section>
    <section><div class="eyebrow">${isExploratory ? 'MODEL ASSUMPTIONS' : 'SIMULATION ASSUMPTIONS'}</div><h2>${isExploratory ? 'Scenario assumptions and boundaries' : 'Evidence and limitations'}</h2>
      ${isExploratory && result.exploratory_scenario ? `<div class="callout"><strong>Census-informed synthetic scenario</strong><br/>${escapeHtml(result.exploratory_scenario.summary)}</div>` : ''}
      <ul>${assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}${assessment.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
      <p><strong>Evidence used:</strong> ${escapeHtml(assessment.evidence_used)}</p>
    </section>
    <footer class="footer">PolicyForge - Chennai-focused synthetic policy decision support. Observed public data, simulation outputs, and AI assumptions are presented as separate evidence types.</footer>
  </body></html>`;
  exportWindow.document.open();
  exportWindow.document.write(report);
  exportWindow.document.close();
  exportWindow.focus();
  window.setTimeout(() => exportWindow.print(), 250);
}
