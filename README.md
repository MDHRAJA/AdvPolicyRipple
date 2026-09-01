# PolicyForge

> **Test policies before they reach people.**

PolicyForge is a Chennai-focused policy decision-support application. It turns a plain-language policy question into either a validated synthetic simulation or a clearly labelled exploratory scenario, then presents the proposed design, trade-offs, ranges, and distributional effects in one results view.

It is designed for discussion, comparison, and presentation—not for autonomous policymaking, an observed forecast of real people, legal advice, engineering design, or budget approval.

## What it does

- **AI Planner**: accepts a blank, user-written policy question and chosen priorities; Gemini interprets it or advises on an outside-catalogue intervention.
- **Simulation catalogue**: supports water rationing/restoration, energy rationing/restoration, rent/zoning change, public transport subsidy, and public subsidy.
- **Policy combinations**: compares a focal supported policy with compatible two-policy bundles before selecting a recommended route.
- **Census-informed synthetic scenarios**: outside-catalogue ideas remain separate from the validated catalogue. Gemini supplies bounded, transparent scenario assumptions; it never relabels them as preset policies.
- **10,000-agent model**: every simulation uses 10,000 synthetic agents. The Chennai preset is anchored to Census 2011 population context.
- **Targeting**: select one or more ward numbers on the map, or leave the selection empty for a citywide application.
- **Results**: combines the policy design, budget and delivery constraint, baseline-versus-policy chart, seeded model range, trajectory, income-group effects, ward overlay, and limitations.
- **Presentation report**: opens a polished print layout that can be saved as PDF. It has a dedicated cover page followed by the policy and evidence pages.
- **Session-only deployment**: Vercel runs without a database; results live in the current browser session and disappear when the session closes.

## Product flow

1. Enter a local policy question in **AI Planner**.
2. Choose the outcomes that matter most.
3. PolicyForge classifies the request.

   - A supported mechanism is configured, compared, simulated, and sent to **Results**.
   - An outside-catalogue mechanism becomes a **Census-informed synthetic scenario** with Gemini’s bounded assumptions shown explicitly.

4. Review the proposal, budget position, charts, uncertainty language, and group-level effects.
5. Export the presentation report if needed.

The simulator can also be used directly when the policy mechanism and parameters are already known.

## Evidence boundaries

PolicyForge keeps evidence types separate.

| Label | What it means |
| --- | --- |
| **OBSERVED DATA** | Public-source Chennai context, official GCC boundaries, and population anchoring. |
| **SIMULATION OUTPUT** | Results created by PolicyForge’s synthetic-agent model. |
| **CENSUS-INFORMED SYNTHETIC SCENARIO** | An outside-catalogue scenario using Census-informed population context and disclosed Gemini/model assumptions. |

The `chennai_census_2011` preset anchors population scale and aggregate context. Individual agents, income bands, behaviour, stress, trust, compliance, policy response, and resulting effects are modelled—not observed facts about people.

For regular catalogue policies, the Results page uses five paired seeded policy-versus-baseline runs to show a model range. This is **not** a statistical confidence interval or empirical forecast. Outside-catalogue scenarios show their assumptions and are not evidence of causal real-world effects.

## Budget handling

A budget and delivery card is shown on every AI Planner result.

- Amounts such as `₹25 lakh`, `2 crores`, `₹2,50,000`, `INR 65,00,000`, and `65 lakhs` are recognised and displayed in Indian rupee formatting.
- A cost/funding concern without an amount—such as “heavy cost”, “strict cost”, or “under this cost”—is still treated as a stated funding consideration.
- The AI must carry a stated funding limit into its policy design, implementation route, actions, and trade-offs.
- PolicyForge does **not** invent a subsidy cut, cost, revenue source, or reallocation.
- A funding constraint changes numerical model results only when a selected simulation mechanism explicitly models that effect. Otherwise it is clearly presented as a delivery/design constraint.

## Ward map

The Ward Map uses official Greater Chennai Corporation boundaries and administrative attributes.

- Search by **ward number** (1–200); this is the reliable identifier exposed by the source.
- Click multiple wards to build a target group.
- **Select all Chennai** clears specific targets and makes the policy citywide.
- Ward effect overlays are synthetic simulation output allocated to official geography; they are not observed ward outcomes.

## Gemini-assisted policy design

Gemini is used server-side only for:

- policy intake and classification;
- supported-policy interpretation;
- specific policy-design advice;
- outside-catalogue scenario assumptions.

The simulator, policy limits, and schema validation remain within PolicyForge. Gemini does not directly supply unvalidated simulator metrics.

Configured Gemini-only fallback order:

1. `gemini-3.6-flash`
2. `gemini-3.5-flash`
3. `gemini-3.5-flash-lite`
4. `gemini-3.1-flash-lite`

Each model uses the same validated request/response contract. A project-wide Gemini quota or credential problem can make AI features unavailable; switching fallback models cannot bypass a project-wide quota.

## Run locally

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Gemini API key only if AI-assisted features are required

### Backend

PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:POLICYFORGE_SESSION_ONLY = 'true'
$env:POLICYFORGE_AI_MODE = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.6-flash'
$env:GEMINI_API_KEY = Read-Host "Paste your Gemini API key"

python -m uvicorn app.main:app --reload --port 8001
```

Paste only the API-key value when prompted—not `GEMINI_API_KEY=`, quotation marks, or spaces.

To run without Gemini, use:

```powershell
$env:POLICYFORGE_AI_MODE = 'rule_based'
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
```

### Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Local browser requests use `http://localhost:8001` by default.

## Private Vercel deployment

The root [vercel.json](vercel.json) defines one Vercel Services project:

| Service | Root | Route |
| --- | --- | --- |
| Next.js interface | `frontend` | `/` |
| FastAPI backend | `backend` | `/api/*` |

The browser calls same-origin `/api/*` routes in Vercel. Do **not** set `NEXT_PUBLIC_API_URL` there, and never expose a Gemini key through a `NEXT_PUBLIC_*` variable.

Set these backend-service environment variables for the environments you deploy:

| Name | Value |
| --- | --- |
| `POLICYFORGE_SESSION_ONLY` | `true` |
| `POLICYFORGE_AI_MODE` | `gemini` |
| `GEMINI_API_KEY` | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-3.6-flash` |
| `GEMINI_FALLBACK_MODEL_1` | `gemini-3.5-flash` |
| `GEMINI_FALLBACK_MODEL_2` | `gemini-3.5-flash-lite` |
| `GEMINI_FALLBACK_MODEL_3` | `gemini-3.1-flash-lite` |
 Vercel deployments are stateless; no Neon or other database is required for the normal session-only mode.

## API overview

| Route | Purpose |
| --- | --- |
| `GET /health` | Health status |
| `GET /api/policies` | Supported policy catalogue |
| `GET /api/populations` | Synthetic population presets |
| `GET /api/observed/chennai` | Observed Chennai context |
| `GET /api/observed/chennai/summary` | Evidence summary |
| `GET /api/observed/chennai/wards` | Official GCC ward layer |
| `POST /api/simulations/run` | Run a stateless simulation |
| `POST /api/assessment` | Produce paired model-range assessment |
| `POST /api/ai/triage` | Classify a policy question |
| `POST /api/ai/policy-plan` | Interpret a supported policy request |
| `POST /api/ai/policy-advice` | Produce Gemini policy design advice |
| `POST /api/ai/exploratory-scenario` | Create an outside-catalogue scenario |
| `POST /api/ai/recommendation` | Compare supported policy options |

## Testing and validation

Run the automated backend suite:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

Run the production frontend check:

```powershell
cd frontend
npm ci
npm run build
```

GitHub Actions runs both checks on every push and pull request:

```text
Backend:  python -m pytest
Frontend: npm run build
```

The test suite covers deterministic simulation runs, policy parameter validation, policy application semantics, income and ward outputs, paired assessment ranges, access-gate behaviour, Gemini request/fallback handling, budget-constraint recognition, AI route classification, and outside-catalogue scenario boundaries.

For the recommended manual checks—including access gate, planner routes, budget display, targeting, report print layout, and Vercel deployment—see [TESTING.md](TESTING.md).

## Repository guide

- [ARCHITECTURE.md](ARCHITECTURE.md) — components and data flow
- [CALIBRATION.md](CALIBRATION.md) — calibration boundaries
- [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) — Vercel Services deployment details
- [TESTING.md](TESTING.md) — automated and manual validation checklist

## Important limitations

- Synthetic agents are not real residents.
- Results are decision-support signals, not population forecasts.
- Observed Census and municipal data anchor context; they do not prove behavioural effects or policy causality.
- Budget, legal, operational, and engineering constraints require real-world review.
- Ward geometries do not imply observed ward-level socioeconomic or service outcomes.
- AI policy advice is useful for policy design discussion but must be reviewed by relevant experts before implementation.
