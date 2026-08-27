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
PHRASE_SIGNALS = {
    'water_rationing': ('water shortage', 'water scarcity', 'drinking water'),
    'energy_rationing': ('power cut', 'energy shortage', 'electricity outage'),
    'rent_zoning': ('housing cost', 'rent burden', 'affordable housing'),
    'transport_subsidy': ('public transport', 'bus fare', 'metro fare'),
    'public_subsidy': ('cost of living', 'financial relief', 'cash support'),
}

OBJECTIVES = {
    'reduce_stress': ('stress', 'hardship', 'pressure'),
    'improve_access': ('access', 'availability', 'service'),
    'reduce_inequality': ('fair', 'inequality', 'equity', 'low income'),
    'build_trust': ('trust', 'confidence', 'legitimacy'),
    'improve_compliance': ('compliance', 'adoption', 'follow'),
}

def _policy_scores(text):
    """Use single terms and stronger multi-word signals to interpret plain language."""
    return {
        policy_id: sum(word in text for word in words) + 3 * sum(phrase in text for phrase in PHRASE_SIGNALS[policy_id])
        for policy_id, words in KEYWORDS.items()
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
    scores = _policy_scores(text)
    selected = max(scores, key=scores.get)
    if scores[selected] == 0:
        selected = 'public_subsidy' if any(word in text for word in ('support', 'help', 'relief')) else 'water_rationing'
    policy = get_policy(selected)
    matched_signals = [signal for signal in (*KEYWORDS[selected], *PHRASE_SIGNALS[selected]) if signal in text]
    parameter_name, default = next(iter(policy['parameters'].items()))
    value = _percentage(text, default)
    if parameter_name == 'cost_change' and value:
        value = -value if any(word in text for word in ('reduce', 'lower', 'affordable')) else value
    normalized_objectives = objectives or [name for name, words in OBJECTIVES.items() if any(word in text for word in words)]
    if not normalized_objectives:
        normalized_objectives = ['improve_access', 'reduce_stress']
    preset = 'chennai_census_2011' if 'chennai' in text else 'balanced'
    config = SimulationConfig(population=PopulationConfig(preset=preset, size=10000), policy_id=selected, policy_parameters={parameter_name: value}, rounds=rounds, seed=seed)
    return {'interpretation': f"PolicyForge interpreted this as {policy['name']} with {parameter_name.replace('_', ' ')} set to {round(value * 100)}%, based on: {', '.join(matched_signals) or 'the overall problem description'}.", 'assumptions': ['This is a transparent rule-based language interpreter, not an observed behavioural model.', 'You must review and edit the proposed configuration before relying on the results.'], 'objectives': normalized_objectives, 'proposed_config': config.model_dump(), 'matched_policy': policy, 'policy_detail': {'parameter': parameter_name, 'value_percent': round(value * 100, 1), 'population_basis': 'Chennai Census 2011 anchored synthetic sample' if preset == 'chennai_census_2011' else 'Synthetic city preset', 'run_design': '10,000 agents · 20 rounds unless explicitly changed · seeded and reproducible'}}

def recommend(config, objectives):
    candidates = []
    for policy_id, policy in POLICIES.items():
        parameter_name, value = next(iter(policy['parameters'].items()))
        candidate = config.model_copy(deep=True)
        candidate.policy_id = policy_id
        candidate.policy_parameters = {parameter_name: value}
        outcome = run(candidate)
        final = outcome['final']
        score = sum([(1 - final['stress']) if 'reduce_stress' in objectives else 0, final['resource_access'] if 'improve_access' in objectives else 0, (1 - final['inequality']) if 'reduce_inequality' in objectives else 0, final['trust'] if 'build_trust' in objectives else 0, final['compliance'] if 'improve_compliance' in objectives else 0])
        candidates.append({'policy_id': policy_id, 'name': policy['name'], 'score': round(score, 4), 'preview': final, 'income_groups': outcome['income_group_impacts'], 'implementation': _implementation(policy_id, parameter_name, value)})
    candidates.sort(key=lambda item: item['score'], reverse=True)
    best = candidates[0]
    evidence = []
    if 'improve_access' in objectives:
        evidence.append(f"resource access {best['preview']['resource_access'] * 100:.1f}%")
    if 'reduce_stress' in objectives:
        evidence.append(f"stress {best['preview']['stress'] * 100:.1f}%")
    if 'reduce_inequality' in objectives:
        evidence.append(f"inequality {best['preview']['inequality'] * 100:.1f}%")
    if 'build_trust' in objectives:
        evidence.append(f"trust {best['preview']['trust'] * 100:.1f}%")
    if 'improve_compliance' in objectives:
        evidence.append(f"compliance {best['preview']['compliance'] * 100:.1f}%")
    return {'recommended': best, 'alternatives': candidates[1:3], 'explanation': f"AI rationale: this option ranked first against {', '.join(objectives).replace('_', ' ')} after comparing every supported policy. Its modelled profile is {', '.join(evidence)}.", 'boundary': 'Recommendations rank synthetic simulation outputs against user-selected objectives; they are not implementation advice or empirical forecasts.'}
