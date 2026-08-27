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

def _implementation(policy_id, parameter, value):
    percent = round(abs(value) * 100, 1)
    if policy_id == 'rent_zoning':
        direction = 'reduce' if value < 0 else 'increase'
        return {'parameter': 'housing cost', 'direction': direction, 'value_percent': percent, 'instruction': f'{direction.capitalize()} modeled housing cost by {percent}% through the rent/zoning lever.', 'stages': [f'Start with a {percent}% modeled housing-cost {direction}.', 'Run the 10,000-agent simulation for 20 rounds.', 'Compare stress, access and inequality with the alternatives before changing the percentage.']}
    if parameter == 'reduction':
        return {'parameter': parameter.replace('_', ' '), 'direction': 'reduce', 'value_percent': percent, 'instruction': f'Reduce the modeled resource availability by {percent}%.', 'stages': [f'Start with a {percent}% reduction.', 'Run the 10,000-agent simulation for 20 rounds.', 'Compare stress, access and trust with the alternatives before changing the percentage.']}
    return {'parameter': parameter.replace('_', ' '), 'direction': 'increase', 'value_percent': percent, 'instruction': f'Increase the modeled {parameter.replace("_", " ")} by {percent}%.', 'stages': [f'Start with a {percent}% increase.', 'Run the 10,000-agent simulation for 20 rounds.', 'Compare the selected objectives with the alternatives before changing the percentage.']}

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
    return {'interpretation': f"PolicyForge interpreted this as {policy['name']} with {parameter_name.replace('_', ' ')} set to {round(value * 100)}%.", 'assumptions': ['This is a transparent rule-based language interpreter, not an observed behavioural model.', 'You must review and edit the proposed configuration before relying on the results.'], 'objectives': normalized_objectives, 'proposed_config': config.model_dump(), 'matched_policy': policy, 'policy_detail': {'parameter': parameter_name, 'value_percent': round(value * 100, 1), 'population_basis': 'Chennai Census 2011 anchored synthetic sample' if preset == 'chennai_census_2011' else 'Synthetic city preset', 'run_design': '10,000 agents · 20 rounds unless explicitly changed · seeded and reproducible'}}

def recommend(config, objectives):
    candidates = []
    for policy_id, policy in POLICIES.items():
        parameter_name, value = next(iter(policy['parameters'].items()))
        candidate = config.model_copy(deep=True)
        candidate.policy_id = policy_id
        candidate.policy_parameters = {parameter_name: value}
        final = run(candidate)['final']
        score = sum([(1 - final['stress']) if 'reduce_stress' in objectives else 0, final['resource_access'] if 'improve_access' in objectives else 0, (1 - final['inequality']) if 'reduce_inequality' in objectives else 0, final['trust'] if 'build_trust' in objectives else 0, final['compliance'] if 'improve_compliance' in objectives else 0])
        candidates.append({'policy_id': policy_id, 'name': policy['name'], 'score': round(score, 4), 'preview': final, 'implementation': _implementation(policy_id, parameter_name, value)})
    candidates.sort(key=lambda item: item['score'], reverse=True)
    best = candidates[0]
    return {'recommended': best, 'alternatives': candidates[1:3], 'explanation': f"AI rationale: this option produced the strongest combined synthetic outcome for {', '.join(objectives).replace('_', ' ')} when compared with every supported policy at its documented default percentage.", 'boundary': 'Recommendations rank synthetic simulation outputs against user-selected objectives; they are not implementation advice or empirical forecasts.'}
