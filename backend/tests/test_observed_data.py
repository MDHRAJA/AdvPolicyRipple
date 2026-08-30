from fastapi.testclient import TestClient
from app.core.models import PopulationConfig, SimulationConfig
from app.main import app
from app.services.simulation import run

def test_observed_chennai_has_provenance():
    payload = TestClient(app).get('/api/observed/chennai').json()
    assert payload['evidence_type'] == 'OBSERVED DATA'
    first = payload['metrics'][0]
    for key in ('dataset', 'geography', 'period', 'metric', 'unit', 'source_org', 'source_url', 'evidence_type'):
        assert first[key]
    assert first['metric'] == 'total_population'
    assert first['value'] == 4646732

def test_chennai_anchor_is_not_behavioral_calibration():
    result = run(SimulationConfig(population=PopulationConfig(preset='chennai_census_2011', size=10000)))
    anchor = result['observed_data_anchor']
    assert anchor['observed_population'] == 4646732
    assert anchor['people_per_synthetic_agent'] == 464.6732
    assert 'trust' in anchor['synthetic_only_variables']
    assert result['evidence_labels']['final'] == 'SIMULATION RESULTS'
