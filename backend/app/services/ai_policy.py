import re
from app.core.models import PopulationConfig, SimulationConfig
from app.services.policies import POLICIES, get_policy
from app.services.simulation import run

KEYWORDS = {
    'water_rationing': ('water', 'drought', 'ration', 'shortage'),
    'energy_rationing': ('energy', 'electricity', 'power', 'outage'),
    'rent_zoning': ('rent', 'housing', 'tenant', 'zoning'),
    'transport_subsidy': ('bus', 'metro', 'transport', 'mobility'),
    'public_subsidy': ('subsidy', 'cash', 'income', 'afford'),
}
OBJECTIVES = {
    'reduce_stress': ('stress', 'hardship', 'pressure'),
    'improve_access': ('access', 'availability', 'service'),
    'reduce_inequality': ('fair', 'inequality', 'equity', 'low income'),
    'build_trust': ('trust', 'confidence', 'legitimacy'),
    'improve_compliance': ('compliance', 'adoption', 'follow'),
}

def _percentage(text, default):
    match = re.search(r'(\d{1,2}(?:\.\d+)?)\s*%', text)
    return max(0, min(.8, float(match.group(1)) / 100)) if match else default

def interpret(prompt, objectives, size=10000, rounds=20, seed=42):
    text = prompt.lower()
    scores = {policy_id: sum(word in text for word in words) for policy_id, words in KEYWORDS.items()}
    selected = max(scores, key=scores.get)
    if scores[selected] == 0:
        selected = 'public_subsidy' if any(word in text for word in ('support', 'help', 'relief')) else 'water_rationing'
    policy = get_policy(selected)
    parameter_name, default = next(iter(policy['parameters'].items()))
    value = _percentage(text, default)
    if parameter_name == 'cost_change' and value:
        value = -value if any(word in text for word in ('reduce', 'lower', 'affordable')) else value
    normalized_objectives = objectives or [name for name, words in OBJECTIVES.items() if any(word in text for word in words)]
    if not normalized_objectives:
        normalized_objectives = ['improve_access', 'reduce_stress']
    preset = 'chennai_census_2011' if 'chennai' in text else 'balanced'
    config = SimulationConfig(population=PopulationConfig(preset=preset, size=10000), policy_id=selected, policy_parameters={parameter_name: value}, rounds=rounds, seed=seed)
    return {
        'interpretation': f"PolicyForge interpreted this as {policy['name']} with {parameter_name.replace('_', ' ')} set to {round(value * 100)}%.",
        'assumptions': ['This is a transparent rule-based language interpreter, not an observed behavioural model.', 'You must review and edit the proposed configuration before relying on the results.'],
        'objectives': normalized_objectives,
        'proposed_config': config.model_dump(),
        'matched_policy': policy,
        'policy_detail': {'parameter': parameter_name, 'value_percent': round(value * 100, 1), 'population_basis': 'Chennai Census 2011 anchored synthetic sample' if preset == 'chennai_census_2011' else 'Synthetic city preset', 'run_design': '10,000 agents · 20 rounds unless explicitly changed · seeded and reproducible'},
    }

def recommend(config, objectives):
    candidates = []
    for policy_id, policy in POLICIES.items():
        parameter_name, value = next(iter(policy['parameters'].items()))
        candidate = config.model_copy(deep=True)
        candidate.policy_id = policy_id
        candidate.policy_parameters = {parameter_name: value}
        final = run(candidate)['final']
        score = 0
        score += (1 - final['stress']) if 'reduce_stress' in objectives else 0
        score += final['resource_access'] if 'improve_access' in objectives else 0
        score += (1 - final['inequality']) if 'reduce_inequality' in objectives else 0
        score += final['trust'] if 'build_trust' in objectives else 0
        score += final['compliance'] if 'improve_compliance' in objectives else 0
        candidates.append({'policy_id': policy_id, 'name': policy['name'], 'score': round(score, 4), 'preview': final})
    candidates.sort(key=lambda item: item['score'], reverse=True)
    best = candidates[0]
    return {'recommended': best, 'alternatives': candidates[1:3], 'explanation': f"Recommended because it has the highest objective-weighted score across the selected priorities: {', '.join(objectives)}.", 'boundary': 'Recommendations rank synthetic simulation outputs against user-selected objectives; they are not implementation advice or empirical forecasts.'}
