import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.models import AccessUnlockRequest, SimulationCreate, SimulationConfig, CompareRequest, CalibrationRequest, PolicyPlanRequest
from app.db.store import init_db, create, get, save
from app.services.observed_data import chennai_calibration_anchor, chennai_metrics, chennai_sources, chennai_summary
from app.services.wards import chennai_ward_boundaries, ward_profile
from app.services.policies import list_policies
from app.services.ai_policy import GeminiUnavailableError, interpret, recommend, interpreter_status, policy_advice, triage_policy
from app.services.simulation import PRESETS, run

app = FastAPI(
    title="PolicyForge API",
    version="1.4.0",
    description="Synthetic policy simulation and auditable observed-data provenance",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The Vercel deployment is stateless: browser session storage holds each result.
# Local development can retain the original SQLite-backed flow.
# Vercel functions have an ephemeral, read-only application filesystem.
# They always use browser-session results; local runs retain SQLite unless opted out.
SESSION_ONLY = (
    os.getenv("POLICYFORGE_SESSION_ONLY", "").lower() in {"1", "true", "yes"}
    or bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
)
if not SESSION_ONLY:
    init_db()




ACCESS_PASSWORD_ENV = "POLICYFORGE_ACCESS_PASSWORD"
ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 12
ACCESS_EXEMPT_PATHS = {"/health", "/api/access/status", "/api/access/unlock", "/api/access/verify"}


def _access_password():
    return os.getenv(ACCESS_PASSWORD_ENV, "")


def _access_enabled():
    return bool(_access_password())


def _token_signature(expires_at: int):
    secret = _access_password().encode("utf-8")
    message = f"policyforge-access-v1:{expires_at}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _issue_access_token():
    expires_at = int(time.time()) + ACCESS_TOKEN_TTL_SECONDS
    raw = f"{expires_at}.{_token_signature(expires_at)}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _valid_access_token(token: str | None):
    if not _access_enabled():
        return True
    if not token:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        expires_raw, signature = decoded.split(".", 1)
        expires_at = int(expires_raw)
    except (ValueError, UnicodeDecodeError):
        return False
    return expires_at >= int(time.time()) and hmac.compare_digest(signature, _token_signature(expires_at))


@app.middleware("http")
async def access_gate(request: Request, call_next):
    if request.method == "OPTIONS" or not _access_enabled() or request.url.path in ACCESS_EXEMPT_PATHS:
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not _valid_access_token(token):
        return JSONResponse(status_code=401, content={"detail": "Password required."})
    return await call_next(request)


@app.get("/api/access/status")
def access_status():
    return {"enabled": _access_enabled()}


@app.post("/api/access/unlock")
def access_unlock(request: AccessUnlockRequest):
    configured_password = _access_password()
    if not configured_password:
        return {"enabled": False, "token": None}
    if not hmac.compare_digest(request.password, configured_password):
        raise HTTPException(401, "Incorrect password.")
    return {"enabled": True, "token": _issue_access_token()}


@app.post("/api/access/verify")
def access_verify(request: Request):
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    if not _valid_access_token(token):
        raise HTTPException(401, "Password required.")
    return {"valid": True}


@app.get("/health")
def health():
    return {"status": "ok", "service": "policyforge-api"}


@app.get("/api/policies")
def policies():
    return list_policies()


@app.get("/api/populations")
def populations():
    return [
        {"id": key, "name": value["name"], "synthetic": True, "observed_context": value.get("observed_context", False)}
        for key, value in PRESETS.items()
    ]


@app.get("/api/observed/chennai")
def observed_chennai():
    return {
        "geography": "Chennai",
        "evidence_type": "OBSERVED DATA",
        "metrics": chennai_metrics(),
        "sources": chennai_sources(),
    }


@app.get("/api/observed/chennai/summary")
def observed_chennai_summary():
    return chennai_summary()


@app.get("/api/observed/chennai/wards")
def observed_chennai_wards():
    try:
        return chennai_ward_boundaries()
    except RuntimeError as error:
        raise HTTPException(503, str(error))


@app.get("/api/observed/chennai/wards/{ward_number}")
def observed_chennai_ward(ward_number: str):
    try:
        return ward_profile(ward_number)
    except KeyError:
        raise HTTPException(404, "Ward not found")
    except RuntimeError as error:
        raise HTTPException(503, str(error))


@app.get("/api/observed/chennai/calibration")
def observed_chennai_calibration(size: int = 500):
    if size < 1:
        raise HTTPException(422, "size must be positive")
    return chennai_calibration_anchor(size)


@app.post("/api/simulations/run")
def run_session_simulation(req: SimulationCreate):
    """Run one scenario without server-side storage for browser-session use."""
    return run(req.config)


@app.post("/api/simulations")
def create_simulation(req: SimulationCreate):
    if SESSION_ONLY:
        raise HTTPException(410, "Persistent simulations are disabled for this deployment.")
    return {"simulation_id": create(req.config), "status": "created"}


@app.get("/api/simulations/{sid}")
def simulation(sid: str):
    row = get(sid)
    if not row:
        raise HTTPException(404, "Simulation not found")
    return {"simulation_id": row[0], "config": json.loads(row[1]), "result": json.loads(row[2]) if row[2] else None}


@app.post("/api/simulations/{sid}/run")
def run_sim(sid: str):
    row = get(sid)
    if not row:
        raise HTTPException(404, "Simulation not found")
    result = run(SimulationConfig.model_validate_json(row[1]))
    result["simulation_id"] = sid
    save(sid, result)
    return result


@app.get("/api/simulations/{sid}/results")
def results(sid: str):
    row = get(sid)
    if not row or not row[2]:
        raise HTTPException(404, "Results not available")
    return json.loads(row[2])


@app.post("/api/simulations/compare")
def compare(req: CompareRequest):
    out = []
    for cfg in req.policies:
        cfg.seed = req.base_config.seed
        cfg.rounds = req.base_config.rounds
        cfg.population = req.base_config.population
        out.append({"policy": cfg.policy_id, "result": run(cfg)["final"]})
    return {"results": out}


OBSERVED_CONTEXT_VARIABLES = [
    'total_population', 'male_population', 'female_population',
    'normal_households', 'population_density', 'sex_ratio',
    'literacy_rate', 'work_participation_rate',
]

SYNTHETIC_ONLY_VARIABLES = [
    'income_band', 'resource_access', 'trust', 'stress', 'risk',
    'cooperation', 'support', 'satisfaction', 'compliance',
    'policy_support', 'relocation',
]

ALLOWED_CALIBRATION_MAPPINGS = {}


@app.post("/api/calibration/run")
def calibration(req: CalibrationRequest):
    """Reject behavioral calibration unless a valid observed->simulated mapping is explicitly allowed.

    The current Chennai dataset is contextual provenance only. There are no valid
    behavioral calibration targets in the observed evidence, so this endpoint must
    fail closed instead of inventing a model fit.
    """
    observed_keys = set(req.observed)
    simulated_keys = set(req.simulated)

    if not observed_keys or not simulated_keys:
        return {
            'calibration_available': False,
            'reason': 'No valid behavioral calibration targets are currently available in the observed dataset.',
            'observed_context_variables': OBSERVED_CONTEXT_VARIABLES,
            'synthetic_only_variables': SYNTHETIC_ONLY_VARIABLES,
        }

    invalid_simulated = sorted(simulated_keys & set(SYNTHETIC_ONLY_VARIABLES))
    if invalid_simulated:
        return {
            'calibration_available': False,
            'reason': 'No valid behavioral calibration targets are currently available in the observed dataset.',
            'observed_context_variables': OBSERVED_CONTEXT_VARIABLES,
            'synthetic_only_variables': SYNTHETIC_ONLY_VARIABLES,
            'rejected_simulated_metrics': invalid_simulated,
        }

    candidate_pairs = [
        (observed_key, simulated_key)
        for observed_key in observed_keys
        for simulated_key in simulated_keys
        if (observed_key, simulated_key) in ALLOWED_CALIBRATION_MAPPINGS
    ]
    if not candidate_pairs:
        return {
            'calibration_available': False,
            'reason': 'No valid behavioral calibration targets are currently available in the observed dataset.',
            'observed_context_variables': OBSERVED_CONTEXT_VARIABLES,
            'synthetic_only_variables': SYNTHETIC_ONLY_VARIABLES,
        }

    return {
        'calibration_available': True,
        'reason': 'Explicitly allowed calibration mapping is available.',
        'observed_context_variables': OBSERVED_CONTEXT_VARIABLES,
        'synthetic_only_variables': SYNTHETIC_ONLY_VARIABLES,
        'allowed_mappings': candidate_pairs,
        'parameters': req.parameters,
        'method': 'no-op until an explicitly allowed mapping is added',
    }


@app.post("/api/assessment")
def assessment(req: SimulationCreate):
    """Compare policy and no-policy outcomes across paired seeded simulations.

    Each pair begins with the same generated synthetic population. The reported
    spread is run-to-run model variation, not a statistical confidence interval
    or an empirical forecast.
    """
    seeds = [41, 42, 43, 44, 45]
    policy_vals, baseline_vals = [], []
    for seed in seeds:
        policy_config = req.config.model_copy(update={"seed": seed})
        baseline_config = policy_config.model_copy(deep=True)
        baseline_config.policy_id = None
        baseline_config.policy_parameters = {}
        baseline_config.policy_bundle = []
        policy_vals.append(run(policy_config)["final"])
        baseline_vals.append(run(baseline_config)["final"])

    keys = policy_vals[0]
    expected = {key: round(sum(item[key] for item in policy_vals) / len(seeds), 4) for key in keys}
    best = {key: round(max(item[key] for item in policy_vals), 4) for key in keys}
    worst = {key: round(min(item[key] for item in policy_vals), 4) for key in keys}
    baseline_expected = {key: round(sum(item[key] for item in baseline_vals) / len(seeds), 4) for key in keys}
    changes = {
        key: [policy[key] - baseline[key] for policy, baseline in zip(policy_vals, baseline_vals)]
        for key in keys
    }
    policy_effect = {
        "baseline": baseline_expected,
        "policy": expected,
        "change": {key: round(sum(values) / len(values), 4) for key, values in changes.items()},
        "min_change": {key: round(min(values), 4) for key, values in changes.items()},
        "max_change": {key: round(max(values), 4) for key, values in changes.items()},
        "runs": len(seeds),
        "range_label": "Paired seeded model range; not a statistical confidence interval.",
    }
    return {
        "expected_outcome": expected,
        "best_case": best,
        "worst_case": worst,
        "uncertainty": {key: round(best[key] - worst[key], 4) for key in keys},
        "policy_effect": policy_effect,
        "evidence_used": "Five paired seeded policy-versus-baseline simulation runs.",
        "limitations": [
            "Synthetic agents and behavioral rules.",
            "Observed Chennai data is contextual/anchoring evidence only where explicitly labeled.",
            "The displayed range reflects seeded model variation, not a statistical confidence interval or forecast of actual people.",
        ],
    }


@app.post("/api/recommendation")
def recommendation(payload: dict):
    weights = payload.get("weights", {})
    rows = []
    for name, metrics in payload.get("results", {}).items():
        parts = {
            "equality": 1 - metrics["inequality"],
            "stability": 1 - metrics["stress"],
            "resource_availability": metrics["resource_access"],
            "compliance": metrics["compliance"],
            "institutional_trust": metrics["trust"],
        }
        rows.append({"policy": name, "score": round(sum(parts[key] * weights.get(key, 0) for key in parts), 4), "components": parts, "weights": weights})
    return sorted(rows, key=lambda item: item["score"], reverse=True)


@app.get("/api/ai/status")
def ai_status():
    return interpreter_status()


@app.post("/api/ai/triage")
def ai_policy_triage(payload: dict):
    """Classify a request before selecting any simulation policy."""
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="A policy question is required.")
    return triage_policy(prompt)


@app.post("/api/ai/policy-plan")
def ai_policy_plan(req: PolicyPlanRequest):
    """Return the validated language interpretation immediately.

    The full 10,000-agent policy-combination comparison is requested separately
    by the browser so the user can review the proposed policy without waiting.
    """
    return interpret(req.prompt, req.objectives, req.size, req.rounds, req.seed)


@app.post("/api/ai/policy-advice")
def ai_policy_advice(payload: dict):
    """Return AI-written policy-design advice that is explicitly not simulated."""
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="A policy question is required.")
    objectives = payload.get("objectives", [])
    try:
        return policy_advice(prompt, objectives if isinstance(objectives, list) else [])
    except GeminiUnavailableError as error:
        # Do not silently substitute a local template for an unavailable AI agent.
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/ai/recommendation")
def ai_recommendation(payload: dict):
    """Run the full recommendation comparison after the interpretation is shown."""
    config = SimulationConfig.model_validate(payload.get("config", {}))
    objectives = payload.get("objectives", [])
    return recommend(config, objectives)
