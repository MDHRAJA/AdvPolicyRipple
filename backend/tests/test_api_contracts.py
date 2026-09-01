from fastapi.testclient import TestClient

from app.main import app


def test_access_gate_keeps_health_public_and_protects_api(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_ACCESS_PASSWORD', 'test-password')
    client = TestClient(app)

    assert client.get('/health').status_code == 200
    assert client.get('/api/policies').status_code == 401


def test_access_unlock_allows_a_session_token_to_use_protected_routes(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_ACCESS_PASSWORD', 'test-password')
    client = TestClient(app)

    unlocked = client.post('/api/access/unlock', json={'password': 'test-password'})
    assert unlocked.status_code == 200
    token = unlocked.json()['token']

    protected = client.get('/api/policies', headers={'Authorization': 'Bearer ' + token})
    assert protected.status_code == 200
    assert protected.json()


def test_access_unlock_rejects_an_incorrect_password(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_ACCESS_PASSWORD', 'test-password')
    client = TestClient(app)

    assert client.post('/api/access/unlock', json={'password': 'incorrect'}).status_code == 401


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
    assert result['ward_impacts']
