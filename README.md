# PolicyForge

> **Test policies before they reach people.**

PolicyForge is an AI-assisted policy simulation sandbox. It creates a
**synthetic** population, applies a configurable policy shock, simulates
bounded-rational agents and reports possible emergent effects. It is decision
support, not a prediction of real human behavior.

## Chennai observed-data layer

`data/chennai/observed_metrics.csv` is the normalized, auditable observed
layer. Every value identifies dataset, geography, period, metric, unit, source
organization, source URL and evidence type. `source_catalog.json` documents
all requested source packs and their integration status.

The `chennai_census_2011` synthetic-population preset anchors its sample
scale to the observed 2011 Chennai population. Agent income, water access,
housing tenure, stress, trust, compliance and policy response remain
**synthetic assumptions**, not observed Chennai data.

Successfully normalized observed values:

- Census 2011: Chennai population, sex split, normal households, density, sex
  ratio, literacy, work participation.
- Chennai District Statistical Handbook: selected 2015–16/2016–17 water,
  electricity, building and MTC context metrics.
- MTC: 2015–16 context metrics from the handbook and 2024–25 official
  performance indicators.
- CMRL: official calendar-year passenger journeys for 2022, 2023 and 2024.

Not normalized: ward-level/housing/amenity Census tables, the remaining MTC
annual-report years (2014–15–2023–24), CMRL annual-report years
(2013–14–2024–25) and Chennai Statistical Handbook values outside the
identified tables. They remain catalogued but are not estimated or
fabricated.

See [CALIBRATION.md](CALIBRATION.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Run locally

### Backend
```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run build
```

## API

- `GET /health`
- `GET /api/policies`
- `GET /api/populations`
- `GET /api/observed/chennai`
- `GET /api/observed/chennai/summary`
- `GET /api/observed/chennai/calibration?size=500`
- `POST /api/simulations`
- `POST /api/simulations/{id}/run`
- `POST /api/calibration/run`
- `POST /api/assessment`

## Optional Gemini policy interpretation

PolicyForge runs without an external AI service by default. To opt into Gemini-assisted interpretation, set these **backend-only** environment variables before starting the API:

```powershell
$env:POLICYFORGE_AI_MODE = 'gemini'
$env:GEMINI_API_KEY = 'your_api_key_here'
$env:GEMINI_MODEL = 'gemini-3.7-flash'
```

The Gemini layer can only choose from PolicyForge’s supported policies and bounded parameters; the backend validates its JSON output before running a simulation. It never supplies simulation metrics. To undo or disable the integration, remove `GEMINI_API_KEY` or set `POLICYFORGE_AI_MODE = 'rule_based'`; the built-in interpreter remains the default fallback, including if an Gemini request fails.

## Chennai ward explorer

`/map` displays official Greater Chennai Corporation 2025 ward-boundary geometry and administrative attributes through the GCC GIS FeatureServer. It is an observed administrative boundary layer, not a ward-level socioeconomic, behavioural, or simulation dataset. Clickable ward profiles state this provenance and boundary explicitly; no missing ward indicators are estimated.

## Policy combinations and ward simulation

The simulator supports a primary policy plus one companion policy. Each policy retains its own bounded parameter, and the combination is applied to the same 10,000-agent experiment. For the Chennai preset, a user can select a ward from `/map` and run a targeted scenario. Ward-effect overlays are **SIMULATION OUTPUT**, based on a transparent synthetic allocation of agents to official GCC ward geography; they are not observed ward outcomes or estimates of ward population, household conditions, or behaviour.


## Private Vercel deployment

PolicyForge is prepared for a private two-project Vercel deployment:

- **Web:** set Vercel Root Directory to `frontend`.
- **API:** set Vercel Root Directory to `backend`; it uses `api/index.py` as the FastAPI serverless entry point.
- Create a Neon Postgres database through Vercel, then set its connection string as `DATABASE_URL` in the API project.
- Set `NEXT_PUBLIC_API_URL` in the web project to the API deployment's HTTPS URL.
- Set `CORS_ORIGINS` in the API project to the web deployment URL.
- Enable **Vercel Authentication → All Deployments** for both projects to keep production and previews private.

The Gemini key belongs only in the API project's environment variables. It must never be added to the frontend project or committed to Git.

See [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) for the complete deployment checklist.
