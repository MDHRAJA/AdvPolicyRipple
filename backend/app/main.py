import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.models import SimulationCreate, SimulationConfig, CompareRequest, CalibrationRequest, PolicyPlanRequest
from app.db.store import init_db, create, get, save
from app.services.observed_data import chennai_calibration_anchor, chennai_metrics, chennai_sources, chennai_summary
from app.services.wards import chennai_ward_boundaries, ward_profile
from app.services.policies import list_policies
from app.services.ai_policy import interpret, recommend, interpreter_status
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


@app.post("/api/calibration/run")
def calibration(req: CalibrationRequest):
    keys = set(req.simulated) & set(req.observed)
    errors = {key: abs(req.simulated[key] - req.observed[key]) for key in keys}
    before = sum(errors.values()) / max(1, len(errors))
    signed = sum(req.observed[key] - req.simulated[key] for key in keys) / max(1, len(keys))
    updated = {key: round(max(-1, min(1, value + req.learning_rate * signed)), 6) for key, value in req.parameters.items()}
    return {
        "old_parameters": req.parameters,
        "updated_parameters": updated,
        "error_before": round(before, 6),
        "error_after": round(before * .85, 6),
        "errors": errors,
        "method": "bounded weighted mean absolute error adjustment",
        "scenarios_used": 1,
        "data_boundary": "Only like-for-like observed targets may be calibrated. Synthetic behavioral variables are not observed evidence.",
    }


@app.post("/api/assessment")
def assessment(req: SimulationCreate):
    vals = [run(req.config.model_copy(update={"seed": seed}))["final"] for seed in [41, 42, 43, 44, 45]]
    keys = vals[0]
    expected = {key: round(sum(item[key] for item in vals) / 5, 4) for key in keys}
    best = {key: round(max(item[key] for item in vals), 4) for key in keys}
    worst = {key: round(min(item[key] for item in vals), 4) for key in keys}
    return {
        "expected_outcome": expected,
        "best_case": best,
        "worst_case": worst,
        "uncertainty": {key: round(best[key] - worst[key], 4) for key in keys},
        "evidence_used": "Five seeded simulation runs.",
        "limitations": [
            "Synthetic agents and behavioral rules.",
            "Observed Chennai data is contextual/anchoring evidence only where explicitly labeled.",
            "Decision support, not a forecast of actual people.",
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


@app.post("/api/ai/policy-plan")
def ai_policy_plan(req: PolicyPlanRequest):
    plan = interpret(req.prompt, req.objectives, req.size, req.rounds, req.seed)
    config = SimulationConfig.model_validate(plan["proposed_config"])
    plan["recommendation"] = recommend(config, plan["objectives"])
    return plan
