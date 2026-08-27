import json
import os
import re
from itertools import combinations

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
VALID_OBJECTIVES = set(OBJECTIVES)
OPENAI_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'policy_id': {'type': 'string', 'enum': list(POLICIES)},
        'percentage': {'type': 'number', 'minimum': 0, 'maximum': 80},
        'housing_direction': {'type': 'string', 'enum': ['reduce', 'increase']},
        'objectives': {'type': 'array', 'items': {'type': 'string', 'enum': list(VALID_OBJECTIVES)}},
        'summary': {'type': 'string'},
    },
    'required': ['policy_id', 'percentage', 'housing_direction', 'objectives', 'summary'],
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
        return {'parameter': 'housing cost', 'direction': direction, 'value_percent': percent, 'instruction': f'{direction.capitalize()} modeled housing cost by {percent}% through the rent/zoning lever.'}
    if parameter == 'reduction':
        return {'parameter': parameter.replace('_', ' '), 'direction': 'reduce', 'value_percent': percent, 'instruction': f'Reduce the modeled resource availability by {percent}%.'}
    return {'parameter': parameter.replace('_', ' '), 'direction': 'increase', 'value_percent': percent, 'instruction': f'Increase the modeled {parameter.replace("_", " ")} by {percent}%.'}


def _build_plan(policy_id, percentage, housing_direction, objectives, prompt, source, summary):
    if policy_id not in POLICIES:
        raise ValueError('Unsupported policy selected by interpreter.')
    policy = get_policy(policy_id)
    parameter_name, default = next(iter(policy['parameters'].items()))
    value = max(0, min(.8, float(percentage) / 100)) if percentage is not None else default
    if parameter_name == 'cost_change':
        value = -value if housing_direction == 'reduce' else value
    normalized_objectives = [item for item in objectives if item in VALID_OBJECTIVES]
    if not normalized_objectives:
        normalized_objectives = ['improve_access', 'reduce_stress']
    ward_phrase = re.search(r'\bwards?\s+([0-9,\s-]+(?:and\s+\d{1,3})?)', prompt, re.IGNORECASE)
    target_wards = []
    if ward_phrase:
        target_wards = sorted({str(number) for number in re.findall(r'\d{1,3}', ward_phrase.group(1)) if 1 <= int(number) <= 200}, key=int)
    preset = 'chennai_census_2011' if 'chennai' in prompt.lower() or target_wards else 'balanced'
    config = SimulationConfig(
        population=PopulationConfig(preset=preset, size=10000),
        policy_id=policy_id,
        policy_parameters={parameter_name: value},
        target_wards=target_wards,
        rounds=20,
        seed=42,
    )
    return {
        'interpretation': summary or f'PolicyForge interpreted this as {policy["name"]} with {parameter_name.replace("_", " ")} set to {round(value * 100)}%.',
        'interpretation_source': source,
        'assumptions': [
            'The language layer only selects supported PolicyForge policies and bounded parameters.',
            'Every proposed setting must be reviewed before simulation; simulation outputs remain the source of numeric results.',
            'For Chennai proposals, no ward target means the policy is applied citywide across the synthetic Chennai sample.',
        ],
        'objectives': normalized_objectives,
        'proposed_config': config.model_dump(),
        'matched_policy': policy,
        'policy_detail': {
            'parameter': parameter_name,
            'value_percent': round(abs(value) * 100, 1),
            'population_basis': 'Chennai Census 2011 anchored synthetic sample' if preset == 'chennai_census_2011' else 'Synthetic city preset',
        },
    }


def interpret_rules(prompt, objectives, size=10000, rounds=20, seed=42):
    text = prompt.lower()
    scores = _policy_scores(text)
    selected = max(scores, key=scores.get)
    if scores[selected] == 0:
        selected = 'public_subsidy' if any(word in text for word in ('support', 'help', 'relief')) else 'water_rationing'
    matched_signals = [signal for signal in (*KEYWORDS[selected], *PHRASE_SIGNALS[selected]) if signal in text]
    policy = get_policy(selected)
    parameter_name, default = next(iter(policy['parameters'].items()))
    value = _percentage(text, default)
    direction = 'reduce' if parameter_name == 'cost_change' and any(word in text for word in ('reduce', 'lower', 'affordable')) else 'increase'
    inferred_objectives = objectives or [name for name, words in OBJECTIVES.items() if any(word in text for word in words)]
    summary = f'PolicyForge interpreted this as {policy["name"]} with {parameter_name.replace("_", " ")} set to {round(value * 100)}%, based on: {", ".join(matched_signals) or "the overall problem description"}.'
    plan = _build_plan(selected, value * 100, direction, inferred_objectives, prompt, 'rule_based', summary)
    plan['proposed_config']['rounds'] = rounds
    plan['proposed_config']['seed'] = seed
    return plan


def _interpret_openai(prompt, objectives):
    """Return a constrained plan proposal. No model output is accepted without validation."""
    from openai import OpenAI

    model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
    client = OpenAI(timeout=8.0, max_retries=0)
    system = (
        'You are the PolicyForge policy-intake layer. Select exactly one supported policy and one percentage. '
        'Never invent policies, datasets, outcomes, or evidence. Interpret only the user text. '
        f'Supported policies: {json.dumps({key: value["name"] for key, value in POLICIES.items()})}. '
        f'Allowed objectives: {sorted(VALID_OBJECTIVES)}. '
        'Use housing_direction=reduce only when the user wants housing costs reduced; otherwise use increase. '
        'The summary must state the interpretation, not a prediction or recommendation.'
    )
    response = client.responses.create(
        model=model,
        instructions=system,
        input=f'Policy request: {prompt}\nSelected objectives: {objectives}',
        text={'format': {'type': 'json_schema', 'name': 'policyforge_policy_intake', 'strict': True, 'schema': OPENAI_SCHEMA}},
    )
    proposal = json.loads(response.output_text)
    return _build_plan(
        proposal['policy_id'],
        proposal['percentage'],
        proposal['housing_direction'],
        objectives or proposal['objectives'],
        prompt,
        'openai',
        proposal['summary'],
    )


def interpreter_status():
    """Expose the active interpreter mode without exposing any credentials."""
    openai_enabled = os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() == 'openai'
    has_key = bool(os.getenv('OPENAI_API_KEY'))
    if openai_enabled and has_key:
        return {'configured': 'openai', 'display': 'OpenAI-assisted', 'fallback': 'Local rule-based fallback is used if OpenAI is unavailable.'}
    if openai_enabled:
        return {'configured': 'rule_based', 'display': 'Local rule-based', 'fallback': 'OpenAI mode was requested but no backend API key is configured.'}
    return {'configured': 'rule_based', 'display': 'Local rule-based', 'fallback': 'OpenAI interpretation is currently disabled.'}


def interpret(prompt, objectives, size=10000, rounds=20, seed=42):
    """Use OpenAI only when explicitly enabled; always fall back to local interpretation."""
    enabled = os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() == 'openai'
    if enabled and os.getenv('OPENAI_API_KEY'):
        try:
            plan = _interpret_openai(prompt, objectives)
            plan['proposed_config']['rounds'] = rounds
            plan['proposed_config']['seed'] = seed
            return plan
        except Exception:
            plan = interpret_rules(prompt, objectives, size, rounds, seed)
            plan['assumptions'].append('OpenAI interpretation was unavailable, so the local rule-based interpreter was used.')
            return plan
    return interpret_rules(prompt, objectives, size, rounds, seed)


def recommend(config, objectives):
    """Rank individual policies and every supported two-policy bundle."""
    candidates = []
    policy_sets = [(policy_id,) for policy_id in POLICIES]
    policy_sets.extend(combinations(POLICIES, 2))
    for policy_ids in policy_sets:
        selections, implementations, names = [], [], []
        for policy_id in policy_ids:
            policy = POLICIES[policy_id]
            parameter_name, value = next(iter(policy['parameters'].items()))
            selections.append({'policy_id': policy_id, 'policy_parameters': {parameter_name: value}})
            implementations.append({'policy_id': policy_id, 'name': policy['name'], 'policy_parameters': {parameter_name: value}, **_implementation(policy_id, parameter_name, value)})
            names.append(policy['name'])
        candidate = config.model_copy(deep=True)
        candidate.policy_id = selections[0]['policy_id']
        candidate.policy_parameters = selections[0]['policy_parameters']
        candidate.policy_bundle = selections if len(selections) > 1 else []
        outcome = run(candidate)
        final = outcome['final']
        score = sum([
            (1 - final['stress']) if 'reduce_stress' in objectives else 0,
            final['resource_access'] if 'improve_access' in objectives else 0,
            (1 - final['inequality']) if 'reduce_inequality' in objectives else 0,
            final['trust'] if 'build_trust' in objectives else 0,
            final['compliance'] if 'improve_compliance' in objectives else 0,
        ])
        candidates.append({'policy_id': '+'.join(policy_ids), 'name': ' + '.join(names), 'score': round(score, 4), 'preview': final, 'income_groups': outcome['income_group_impacts'], 'policy_bundle': implementations, 'implementation': implementations[0]})
    candidates.sort(key=lambda item: item['score'], reverse=True)
    best = candidates[0]
    evidence = []
    if 'improve_access' in objectives: evidence.append(f"resource access {best['preview']['resource_access'] * 100:.1f}%")
    if 'reduce_stress' in objectives: evidence.append(f"stress {best['preview']['stress'] * 100:.1f}%")
    if 'reduce_inequality' in objectives: evidence.append(f"inequality {best['preview']['inequality'] * 100:.1f}%")
    if 'build_trust' in objectives: evidence.append(f"trust {best['preview']['trust'] * 100:.1f}%")
    if 'improve_compliance' in objectives: evidence.append(f"compliance {best['preview']['compliance'] * 100:.1f}%")
    return {'recommended': best, 'alternatives': candidates[1:3], 'explanation': f"AI rationale: this option ranked first against {', '.join(objectives).replace('_', ' ')} after comparing individual policies and every supported two-policy bundle. Its modelled profile is {', '.join(evidence)}.", 'boundary': 'Recommendations rank synthetic simulation outputs against user-selected objectives; they are not implementation advice or empirical forecasts.'}
