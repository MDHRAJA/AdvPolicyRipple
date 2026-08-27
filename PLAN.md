# POLICYRIPPLE MVP Plan

## Architecture
Next.js UI → FastAPI API → seeded simulation engine → metrics/assessment. SQLite persists configurations/results. Calibration is explicit and auditable. Optional LLM reasoning can sit behind a provider interface and fall back to rules.

## Data boundaries
- **SYNTHETIC DEMO DATA:** generated populations and demo distributions.
- **SIMULATION RESULTS:** outputs from seeded experiments.
- **OBSERVED DATA:** optional calibration input only.
- **MODEL-INFERRED INSIGHTS:** derived summaries, never presented as observed facts.

## Core workflow
1. Configure population and policy.
2. Generate heterogeneous agents with a seed.
3. Apply policy shock over rounds.
4. Run bounded-rational decisions and local social interactions.
5. Aggregate metrics and unintended-consequence score.
6. Persist result.
7. Compare scenarios or run multi-seed assessment.
8. Optionally calibrate against observed/historical metrics.

## Testing
Backend tests cover reproducibility, policy effects, API health and catalogs. The dashboard uses actual API result data rather than fabricated chart series.
