from fastapi.testclient import TestClient

from app.main import app


def test_health_and_policy_catalog_are_public():
    client = TestClient(app)

    assert client.get('/health').status_code == 200
    policies = client.get('/api/policies')
    assert policies.status_code == 200
    assert policies.json()

def test_stateless_simulation_route_returns_a_complete_result():
    client = TestClient(app)
    response = client.post('/api/simulations/run', json={
        'config': {
            'population': {'preset': 'balanced', 'size': 10000, 'neighborhoods': 4},
            'policy_id': 'water_rationing',
            'policy_parameters': {'reduction': 0.2},
            'rounds': 2,
            'seed': 42,
        },
    })

    assert response.status_code == 200
    result = response.json()
    assert len(result['timeline']) == 2
    assert set(result['income_group_impacts']) == {'low', 'middle', 'high'}
    assert result['evidence_labels']['baseline'] == 'SIMULATION RESULTS'
