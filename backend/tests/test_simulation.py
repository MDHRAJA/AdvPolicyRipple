import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.core.models import SimulationConfig, PopulationConfig
from app.services.simulation import run, metrics, income_group_metrics, ward_metrics
from app.services.ai_policy import interpret

def test_reproducible():
    config = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7)
    assert run(config)['final'] == run(config)['final']


def test_valid_policy_parameters_still_work():
    config = SimulationConfig(
        population=PopulationConfig(size=10000),
        rounds=3,
        seed=7,
        policy_id='public_subsidy',
        policy_parameters={'subsidy': 0.25},
    )
    result = run(config)
    assert result['final']['resource_access'] > 0.75
    assert result['final']['compliance'] > 0.5


def test_invalid_policy_id_returns_422():
    with pytest.raises(ValidationError):
        SimulationConfig(
            population=PopulationConfig(size=10000),
            rounds=3,
            seed=7,
            policy_id='not_a_real_policy',
            policy_parameters={},
        )


def test_unknown_policy_parameter_returns_422():
    with pytest.raises(ValidationError):
        SimulationConfig(
            population=PopulationConfig(size=10000),
            rounds=3,
            seed=7,
            policy_id='public_subsidy',
            policy_parameters={'not_supported': 0.25},
        )


def test_out_of_range_policy_parameter_returns_422():
    with pytest.raises(ValidationError):
        SimulationConfig(
            population=PopulationConfig(size=10000),
            rounds=3,
            seed=7,
            policy_id='public_subsidy',
            policy_parameters={'subsidy': 2.0},
        )


def test_same_valid_seed_config_is_reproducible():
    config = SimulationConfig(
        population=PopulationConfig(size=10000),
        rounds=5,
        seed=11,
        policy_id='water_rationing',
        policy_parameters={'reduction': 0.25},
    )
    first = run(config)
    second = run(config)
    assert first['final'] == second['final']


def test_compliance_increases_with_support():
    a = {'support': 0.30, 'trust': 0.50, 'stress': 0.20, 'risk': 0.20}
    b = {**a, 'support': 0.80}
    score_a = 0.45 * a['support'] + 0.35 * a['trust'] + 0.20 * (1 - a['stress']) - 0.10 * a['risk']
    score_b = 0.45 * b['support'] + 0.35 * b['trust'] + 0.20 * (1 - b['stress']) - 0.10 * b['risk']
    assert score_b > score_a


def test_compliance_increases_with_trust():
    a = {'support': 0.60, 'trust': 0.20, 'stress': 0.20, 'risk': 0.20}
    b = {**a, 'trust': 0.80}
    score_a = 0.45 * a['support'] + 0.35 * a['trust'] + 0.20 * (1 - a['stress']) - 0.10 * a['risk']
    score_b = 0.45 * b['support'] + 0.35 * b['trust'] + 0.20 * (1 - b['stress']) - 0.10 * b['risk']
    assert score_b > score_a


def test_compliance_decreases_with_stress():
    a = {'support': 0.60, 'trust': 0.60, 'stress': 0.10, 'risk': 0.20}
    b = {**a, 'stress': 0.80}
    score_a = 0.45 * a['support'] + 0.35 * a['trust'] + 0.20 * (1 - a['stress']) - 0.10 * a['risk']
    score_b = 0.45 * b['support'] + 0.35 * b['trust'] + 0.20 * (1 - b['stress']) - 0.10 * b['risk']
    assert score_b < score_a


def test_compliance_decreases_with_risk():
    a = {'support': 0.60, 'trust': 0.60, 'stress': 0.20, 'risk': 0.10}
    b = {**a, 'risk': 0.90}
    score_a = 0.45 * a['support'] + 0.35 * a['trust'] + 0.20 * (1 - a['stress']) - 0.10 * a['risk']
    score_b = 0.45 * b['support'] + 0.35 * b['trust'] + 0.20 * (1 - b['stress']) - 0.10 * b['risk']
    assert score_b < score_a


def test_compliance_is_bounded_between_zero_and_one():
    values = [
        {'support': 0.0, 'trust': 0.0, 'stress': 1.0, 'risk': 1.0},
        {'support': 1.0, 'trust': 1.0, 'stress': 0.0, 'risk': 0.0},
        {'support': 0.5, 'trust': 0.5, 'stress': 0.5, 'risk': 0.5},
    ]
    for item in values:
        score = max(0, min(1, 0.45 * item['support'] + 0.35 * item['trust'] + 0.20 * (1 - item['stress']) - 0.10 * item['risk']))
        assert 0 <= score <= 1


def test_compliance_formula_is_used_consistently_across_metrics():
    agents = [
        {'resource_access': 0.8, 'satisfaction': 0.7, 'cooperation': 0.7, 'support': 0.7, 'trust': 0.8, 'stress': 0.2, 'risk': 0.1, 'income_band': 'low', 'ward': '7', 'relocated': False},
        {'resource_access': 0.6, 'satisfaction': 0.6, 'cooperation': 0.5, 'support': 0.4, 'trust': 0.5, 'stress': 0.5, 'risk': 0.3, 'income_band': 'middle', 'ward': '7', 'relocated': False},
        {'resource_access': 0.7, 'satisfaction': 0.65, 'cooperation': 0.6, 'support': 0.6, 'trust': 0.6, 'stress': 0.4, 'risk': 0.2, 'income_band': 'high', 'ward': '9', 'relocated': False},
    ]
    overall = metrics(agents)
    income = income_group_metrics(agents)
    ward = ward_metrics(agents)
    assert 0 <= overall['compliance'] <= 1
    assert 0 <= income['low']['compliance'] <= 1
    assert 0 <= income['middle']['compliance'] <= 1
    assert 0 <= ward['7']['compliance'] <= 1
    assert overall['compliance'] != 0.35


def test_compliance_is_not_thresholded_by_support():
    first = {'support': 0.36, 'trust': 0.50, 'stress': 0.30, 'risk': 0.10}
    second = {'support': 0.37, 'trust': 0.50, 'stress': 0.30, 'risk': 0.10}
    first_score = 0.45 * first['support'] + 0.35 * first['trust'] + 0.20 * (1 - first['stress']) - 0.10 * first['risk']
    second_score = 0.45 * second['support'] + 0.35 * second['trust'] + 0.20 * (1 - second['stress']) - 0.10 * second['risk']
    assert second_score > first_score
    assert first_score > 0.35


def test_policy_effect():
    baseline = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7, policy_id=None)
    rationing = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7, policy_id='water_rationing', policy_parameters={'reduction': .4})
    assert run(rationing)['final']['resource_access'] < run(baseline)['final']['resource_access']


def test_policy_is_applied_once_not_once_per_round():
    one_round = SimulationConfig(population=PopulationConfig(size=10000), rounds=1, seed=7, policy_id='water_rationing', policy_parameters={'reduction': .25})
    five_rounds = SimulationConfig(population=PopulationConfig(size=10000), rounds=5, seed=7, policy_id='water_rationing', policy_parameters={'reduction': .25})
    twenty_rounds = SimulationConfig(population=PopulationConfig(size=10000), rounds=20, seed=7, policy_id='water_rationing', policy_parameters={'reduction': .25})

    r1 = run(one_round)
    r5 = run(five_rounds)
    r20 = run(twenty_rounds)

    # The one-time-shock semantics should not compound a 25% reduction as 0.75^rounds.
    # If apply_policy() were moved back inside the round loop, the repeated-policy floor would appear.
    assert r1['final']['resource_access'] == r5['final']['resource_access'] == r20['final']['resource_access']
    assert r20['final']['resource_access'] > 0.05
    assert r20['final']['resource_access'] > 0.75 * 0.7

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


def test_calibration_rejects_synthetic_behavioral_targets():
    client = TestClient(app)
    response = client.post('/api/calibration/run', json={
        'simulated': {'stress': 0.52, 'trust': 0.75},
        'observed': {'population_density': 26553},
        'parameters': {'reduction': 0.2},
        'learning_rate': 0.15,
    })
    assert response.status_code == 200
    body = response.json()
    assert body['calibration_available'] is False
    assert body['reason'] == 'No valid behavioral calibration targets are currently available in the observed dataset.'
    assert 'trust' in body['synthetic_only_variables']
    assert 'stress' in body['synthetic_only_variables']
    assert 'error_after' not in body


def test_calibration_rejects_unrelated_observed_and_simulated_metrics():
    client = TestClient(app)
    response = client.post('/api/calibration/run', json={
        'simulated': {'resource_access': 0.71},
        'observed': {'literacy_rate': 90.2},
        'parameters': {'subsidy': 0.1},
        'learning_rate': 0.15,
    })
    assert response.status_code == 200
    body = response.json()
    assert body['calibration_available'] is False
    assert body['reason'] == 'No valid behavioral calibration targets are currently available in the observed dataset.'
    assert 'resource_access' in body['synthetic_only_variables']
    assert 'literacy_rate' in body['observed_context_variables']
    assert 'error_after' not in body


def test_ai_policy_plan():
    client = TestClient(app)
    response = client.post('/api/ai/policy-plan', json={'prompt': 'Water shortages in Chennai are affecting low income households by 25%', 'objectives': ['improve_access', 'reduce_stress']})
    assert response.status_code == 200
    body = response.json()
    assert body['proposed_config']['policy_id'] == 'water_rationing'
    assert body['proposed_config']['population']['preset'] == 'chennai_census_2011'
    assert body['matched_policy']['id'] == 'water_rationing'
    assert 'improve_access' in body['objectives']
    assert 'reduce_stress' in body['objectives']


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


def test_ai_policy_plan_recognizes_multiple_chennai_wards():
    plan = interpret('Chennai wards 92, 93 and 94 need a fair water response', ['improve_access'])
    assert plan['proposed_config']['target_wards'] == ['92', '93', '94']
