import json
import os
import re
from itertools import combinations

import httpx

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
GEMINI_SCHEMA = {
    'type': 'object',
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


def _water_restoration_context(text):
    """Distinguish restoring water availability from imposing a new water cut."""
    has_water = 'water' in text
    restoration = bool(re.search(r'\b(increas(?:e|ing)|restore|restor(?:e|ing)|raise)\b[^.]{0,60}\b(?:available\s+)?water', text))
    if not (has_water and restoration):
        return None
    change = _percentage(text, 0)
    current = re.search(r'\b(?:current|existing|present)\s+(?:water\s+)?(?:cut|ration(?:ing)?)\s*(?:is|of|at)?\s*(\d{1,2}(?:\.\d+)?)\s*%', text)
    if not current:
        return {
            'target_cut': None,
            'summary': 'The request increases water availability, but does not state the current water-cut baseline. PolicyForge will not convert that into a rationing percentage without a baseline.',
        }
    existing_cut = max(0, min(.8, float(current.group(1)) / 100))
    target_cut = max(0, existing_cut - change)
    return {
        'target_cut': target_cut,
        'summary': f'Water availability is restored by {change * 100:.1f} percentage points: the stated {existing_cut * 100:.1f}% water cut becomes a {target_cut * 100:.1f}% target cut.',
    }


def _fiscal_consideration(text):
    if not any(term in text for term in ('budget', 'fund', 'funds', 'money', 'cost', 'afford')):
        return None
    return (
        'Budget preservation is recognised as a constraint. PolicyForge will not silently invent a reduction to another subsidy: '
        'the request does not identify the programme, current allocation, protected groups, or amount that can be reallocated. '
        'Specify that trade-off explicitly before treating it as a simulation input.'
    )


def _implementation(policy_id, parameter, value):
    """Give each policy a direct, human-readable implementation description."""
    percent = round(abs(value) * 100, 1)
    if policy_id == 'water_rationing':
        return {'parameter': 'water availability', 'direction': 'reduce', 'value_percent': percent, 'instruction': f'Temporarily reduce household water availability by {percent}% during constrained periods.'}
    if policy_id == 'energy_rationing':
        return {'parameter': 'energy availability', 'direction': 'reduce', 'value_percent': percent, 'instruction': f'Temporarily reduce household energy availability by {percent}% during constrained periods.'}
    if policy_id == 'rent_zoning':
        direction = 'reduce' if value < 0 else 'increase'
        return {'parameter': 'housing cost', 'direction': direction, 'value_percent': percent, 'instruction': f'{direction.capitalize()} housing cost by {percent}% through rent and zoning adjustments.'}
    if policy_id == 'public_subsidy':
        return {'parameter': 'public subsidy', 'direction': 'increase', 'value_percent': percent, 'instruction': f'Increase public subsidy support by {percent}%.'}
    if policy_id == 'transport_subsidy':
        return {'parameter': 'public transport subsidy', 'direction': 'increase', 'value_percent': percent, 'instruction': f'Increase the public transport subsidy by {percent}%.'}
    return {'parameter': parameter.replace('_', ' '), 'direction': 'increase', 'value_percent': percent, 'instruction': f'Increase {parameter.replace("_", " ")} by {percent}%.'}

def _build_plan(policy_id, percentage, housing_direction, objectives, prompt, source, summary, fiscal_consideration=None):
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
        'fiscal_consideration': fiscal_consideration,
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
    water_context = _water_restoration_context(text)
    if selected == 'water_rationing' and water_context and water_context['target_cut'] is not None:
        value = water_context['target_cut']
    direction = 'reduce' if parameter_name == 'cost_change' and any(word in text for word in ('reduce', 'lower', 'affordable')) else 'increase'
    inferred_objectives = objectives or [name for name, words in OBJECTIVES.items() if any(word in text for word in words)]
    summary = water_context['summary'] if selected == 'water_rationing' and water_context else f'PolicyForge interpreted this as {policy["name"]} with {parameter_name.replace("_", " ")} set to {round(value * 100)}%, based on: {", ".join(matched_signals) or "the overall problem description"}.'
    plan = _build_plan(selected, value * 100, direction, inferred_objectives, prompt, 'rule_based', summary, _fiscal_consideration(text))
    plan['proposed_config']['rounds'] = rounds
    plan['proposed_config']['seed'] = seed
    return plan


def _interpret_gemini(prompt, objectives):
    """Interpret the request with Gemini, then validate every returned field locally."""
    model = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    system = (
        "You are the PolicyForge policy-intake layer. Select exactly one supported policy and one percentage. "
        "Never invent policies, datasets, outcomes, or evidence. Interpret only the user text. "
        f"Supported policies: {json.dumps({key: value['name'] for key, value in POLICIES.items()})}. "
        f"Allowed objectives: {sorted(VALID_OBJECTIVES)}. "
        "Use housing_direction=reduce only when the user wants housing costs reduced; otherwise use increase. "
        "A stated increase in water availability is not a new water cut. If the request gives a current water cut and an availability restoration, return the remaining target cut after subtracting the restoration. "
        "The summary must state the interpretation, not a prediction or recommendation."
    )
    response = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
        json={
            "model": model,
            "input": f"{system}\n\nPolicy request: {prompt}\nSelected objectives: {objectives}",
            "store": False,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": GEMINI_SCHEMA,
            },
        },
        timeout=12.0,
    )
    response.raise_for_status()
    payload = response.json()
    output = payload.get("output_text")
    if not output:
        for step in reversed(payload.get("steps", [])):
            for content in step.get("content", []):
                if content.get("type") == "text" and content.get("text"):
                    output = content["text"]
                    break
            if output:
                break
    if not output:
        raise ValueError("Gemini returned no structured policy interpretation.")
    proposal = json.loads(output)
    water_context = _water_restoration_context(prompt)
    percentage = proposal["percentage"]
    summary = proposal["summary"]
    if proposal["policy_id"] == 'water_rationing' and water_context and water_context['target_cut'] is not None:
        percentage = water_context['target_cut'] * 100
        summary = water_context['summary']
    return _build_plan(
        proposal["policy_id"],
        percentage,
        proposal["housing_direction"],
        objectives or proposal["objectives"],
        prompt,
        "gemini",
        summary,
        _fiscal_consideration(prompt),
    )


def interpreter_status():
    """Expose the active interpreter without exposing credentials."""
    gemini_enabled = os.getenv("POLICYFORGE_AI_MODE", "rule_based").lower() == "gemini"
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    if gemini_enabled and has_key:
        return {"configured": "gemini", "display": "Gemini-assisted", "fallback": "Local rule-based fallback is used if Gemini is unavailable."}
    if gemini_enabled:
        return {"configured": "rule_based", "display": "Local rule-based", "fallback": "Gemini mode was requested but no backend API key is configured."}
    return {"configured": "rule_based", "display": "Local rule-based", "fallback": "Gemini interpretation is currently disabled."}


def interpret(prompt, objectives, size=10000, rounds=20, seed=42):
    """Use Gemini only when explicitly enabled; always fall back to local interpretation."""
    enabled = os.getenv("POLICYFORGE_AI_MODE", "rule_based").lower() == "gemini"
    if enabled and os.getenv("GEMINI_API_KEY"):
        try:
            plan = _interpret_gemini(prompt, objectives)
            plan["proposed_config"]["rounds"] = rounds
            plan["proposed_config"]["seed"] = seed
            return plan
        except Exception:
            plan = interpret_rules(prompt, objectives, size, rounds, seed)
            plan["assumptions"].append("Gemini interpretation was unavailable, so the local rule-based interpreter was used.")
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
