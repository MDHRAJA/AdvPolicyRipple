import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHENNAI_DIR = ROOT / 'data' / 'chennai'
METRICS_FILE = CHENNAI_DIR / 'observed_metrics.csv'
SOURCES_FILE = CHENNAI_DIR / 'source_catalog.json'

def _coerce(value: str):
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

def chennai_metrics():
    with METRICS_FILE.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row['value'] = _coerce(row['value'])
    return rows

def chennai_sources():
    return json.loads(SOURCES_FILE.read_text(encoding='utf-8'))

def chennai_calibration_anchor(sample_size: int):
    """Return observed scale/provenance, never behavioral calibration values."""
    metrics = {row['metric']: row['value'] for row in chennai_metrics()}
    total = metrics['total_population']
    return {
        'evidence_type': 'OBSERVED DATA',
        'anchor': 'Chennai Census 2011 total population',
        'reference_year': 2011,
        'observed_population': total,
        'synthetic_sample_size': sample_size,
        'people_per_synthetic_agent': total / sample_size,
        'observed_context_variables': [
            'total_population', 'male_population', 'female_population',
            'normal_households', 'population_density', 'sex_ratio',
            'literacy_rate', 'work_participation_rate',
        ],
        'synthetic_only_variables': [
            'income_band', 'resource_access', 'trust', 'stress', 'risk',
            'cooperation', 'support', 'satisfaction', 'compliance',
        ],
        'provenance': 'data/chennai/observed_metrics.csv',
    }

def chennai_summary():
    rows = chennai_metrics()
    by_domain = defaultdict(list)
    domain_map = {
        'population': {'total_population', 'male_population', 'female_population', 'normal_households', 'population_density', 'sex_ratio', 'literacy_rate', 'work_participation_rate'},
        'water': {'water_house_connections', 'water_supply_normal', 'water_supply_drought'},
        'energy': {'domestic_electricity_consumption', 'total_electricity_consumption'},
        'housing': {'private_buildings_completed', 'public_buildings_completed'},
        'transport_bus': {'mtc_fleet_strength', 'mtc_scheduled_services', 'mtc_occupancy', 'mtc_passengers_per_day', 'mtc_effective_km', 'mtc_routes'},
        'transport_metro': {'cmrl_annual_passengers'},
    }
    for row in rows:
        for domain, metrics in domain_map.items():
            if row['metric'] in metrics:
                by_domain[domain].append(row)
                break
    return {
        'geography': 'Chennai',
        'evidence_type': 'OBSERVED DATA',
        'domains': dict(by_domain),
        'metric_count': len(rows),
        'limitations': [
            'The observed datasets have different reference years and must not be treated as one contemporaneous snapshot.',
            'Census demographic baselines are from 2011.',
            'The district statistical handbook contains mainly 2015-16 and 2016-17 observations.',
            'MTC and CMRL transport observations are more recent but use metropolitan/network geographies that are not identical to Chennai district.',
            'Stress, institutional trust, cooperation, policy support and compliance remain simulation assumptions, not observed Chennai measurements.',
        ],
    }
