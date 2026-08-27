from fastapi.testclient import TestClient
from app.main import app
from app.core.models import SimulationConfig, PopulationConfig
from app.services.simulation import run

def test_reproducible():
    config = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7)
    assert run(config)['final'] == run(config)['final']

def test_policy_effect():
    baseline = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7, policy_parameters={'reduction': 0})
    rationing = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7, policy_parameters={'reduction': .4})
    assert run(rationing)['final']['resource_access'] < run(baseline)['final']['resource_access']

def test_health_and_catalogs():
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert len(client.get('/api/policies').json()) >= 5
    populations = client.get('/api/populations').json()
    assert len(populations) >= 4
    assert any(row['id'] == 'chennai_census_2011' and row['observed_context'] for row in populations)

def test_simulation_lifecycle():
    client = TestClient(app)
    config = {'population': {'preset': 'balanced', 'size': 10000, 'neighborhoods': 4}, 'policy_id': 'water_rationing', 'policy_parameters': {'reduction': 0.2}, 'rounds': 3, 'seed': 11}
    created = client.post('/api/simulations', json={'config': config})
    assert created.status_code == 200
    sid = created.json()['simulation_id']
    executed = client.post(f'/api/simulations/{sid}/run')
    assert executed.status_code == 200
    assert executed.json()['simulation_id'] == sid
    results = client.get(f'/api/simulations/{sid}/results')
    assert results.status_code == 200
    assert len(results.json()['timeline']) == 3

def test_assessment_returns_uncertainty():
    client = TestClient(app)
    config = {'population': {'preset': 'balanced', 'size': 10000, 'neighborhoods': 4}, 'policy_id': 'water_rationing', 'policy_parameters': {'reduction': 0.2}, 'rounds': 2, 'seed': 11}
    response = client.post('/api/assessment', json={'config': config})
    assert response.status_code == 200
    body = response.json()
    assert {'expected_outcome', 'best_case', 'worst_case', 'uncertainty'} <= body.keys()


def test_ai_policy_plan():
    client = TestClient(app)
    response = client.post('/api/ai/policy-plan', json={'prompt': 'Water shortages in Chennai are affecting low income households by 25%', 'objectives': ['improve_access', 'reduce_stress']})
    assert response.status_code == 200
    assert response.json()['proposed_config']['policy_id'] == 'water_rationing'
