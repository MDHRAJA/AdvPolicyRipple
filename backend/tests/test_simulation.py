from fastapi.testclient import TestClient
from app.main import app
from app.core.models import SimulationConfig, PopulationConfig
from app.services.simulation import run
from app.services.ai_policy import interpret

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
    body = response.json()
    assert body['proposed_config']['policy_id'] == 'water_rationing'
    assert set(body['recommendation']['recommended']['income_groups']) == {'low', 'middle', 'high'}
    assert 1 <= len(body['recommendation']['recommended']['policy_bundle']) <= 2


def test_income_group_impacts_are_returned():
    config = SimulationConfig(population=PopulationConfig(size=10000), rounds=1, seed=7)
    impacts = run(config)['income_group_impacts']
    assert set(impacts) == {'low', 'middle', 'high'}
    assert all('stress' in impacts[group]['change'] for group in impacts)


def test_openai_mode_without_key_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_AI_MODE', 'openai')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    plan = interpret('Reduce housing costs in Chennai by 20%', ['reduce_stress'])
    assert plan['interpretation_source'] == 'rule_based'
    assert plan['proposed_config']['policy_id'] == 'rent_zoning'
    assert plan['proposed_config']['policy_parameters']['cost_change'] == -.2


def test_ward_service_metadata_is_not_simulation_data():
    from app.services.wards import GCC_WARD_SERVICE, GCC_WARD_SOURCE
    assert 'FeatureServer/2/query' in GCC_WARD_SERVICE
    assert GCC_WARD_SOURCE.startswith('https://gisgcc.chennaicorporation.gov.in/')


def test_chennai_ward_impacts_and_policy_bundle():
    config = SimulationConfig(population=PopulationConfig(preset='chennai_census_2011', size=10000), policy_id='water_rationing', policy_bundle=[{'policy_id': 'public_subsidy', 'policy_parameters': {'subsidy': .2}}], target_wards=['1'], rounds=1, seed=7)
    result = run(config)
    assert result['ward_impact_evidence_type'] == 'SIMULATION OUTPUT'
    assert '1' in result['ward_impacts']
    assert result['policy_bundle'] == ['public_subsidy']


def test_ai_policy_plan_recognizes_chennai_ward_target():
    plan = interpret('Chennai Ward 92 needs a fair water response', ['improve_access'])
    assert plan['proposed_config']['population']['preset'] == 'chennai_census_2011'
    assert plan['proposed_config']['target_wards'] == ['92']
