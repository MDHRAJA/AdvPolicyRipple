# Chennai observed-data and calibration boundary

POLICYRIPPLE labels evidence in three separate classes:

- **OBSERVED DATA**: external, aggregate facts stored in
  `data/chennai/observed_metrics.csv`, including source organization, URL,
  period, geography, metric and unit.
- **SYNTHETIC DATA / SIMULATION ASSUMPTIONS**: agent attributes and behavioral
  rules.
- **SIMULATION RESULTS**: outputs of seeded runs.

## Anchoring the Chennai sample

Select `chennai_census_2011` to create a synthetic sample whose scale is
anchored to the 2011 Census total population (4,646,732). The API returns the
observed population and the people-per-synthetic-agent scale factor. It does
not convert aggregate Census, water, transport, housing or energy facts into
individual income, resource access, trust, stress, compliance or policy
response. Those remain synthetic until like-for-like observed measurements are
available.

Use:

- `GET /api/observed/chennai` for all normalized observations and sources.
- `GET /api/observed/chennai/calibration?size=500` for the scale anchor.

The generic calibration endpoint must receive only comparable targets. It must
not be used to label synthetic behavioral variables as observed.
