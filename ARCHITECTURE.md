# Architecture

```text
Official public-agency sources
   ↓ validated extraction
data/chennai/observed_metrics.csv + source_catalog.json
   ↓ explicit scale/context anchor
FastAPI API ─── SQLite persistence
   ↓
Seeded Simulation Engine
   ├── Synthetic Population
   ├── Policy Registry
   ├── Agent Decisions
   ├── Social Interaction
   └── Metrics
          ↓
   Comparison / Calibration / Assessment
          ↓
       Next.js dashboard
```

Observed data, synthetic inputs and simulation results have separate labels.
The Chennai Census preset uses observed population only to anchor sample scale;
it does not turn aggregate observations into behavioral rules. The source
catalog records scope, time coverage and extractability for every requested
dataset, including reports that were found but not normalized.
