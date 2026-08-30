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
    'water_service_restoration': ('water', 'restore', 'restoration', 'availability', 'supply'),
    'energy_rationing': ('energy', 'electricity', 'power', 'outage'),
    'energy_service_restoration': ('energy', 'electricity', 'power', 'restore', 'restoration', 'availability'),
    'rent_zoning': ('rent', 'housing', 'tenant', 'zoning'),
    'transport_subsidy': ('bus', 'metro', 'transport', 'mobility'),
    'public_subsidy': ('subsidy', 'cash', 'income', 'afford'),
}
PHRASE_SIGNALS = {
    'water_rationing': ('water shortage', 'water scarcity', 'drinking water'),
    'water_service_restoration': ('increase water availability', 'available water', 'water service restoration', 'restore water'),
    'energy_rationing': ('power cut', 'energy shortage', 'electricity outage'),
    'energy_service_restoration': ('increase electricity availability', 'restore electricity', 'restore power', 'energy service restoration'),
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
            'restoration': change,
            'summary': f'Increase household water availability by {change * 100:.1f}%. This is treated as water service restoration, not a new water cut.',
        }
    existing_cut = max(0, min(.8, float(current.group(1)) / 100))
    target_cut = max(0, existing_cut - change)
    return {
        'restoration': change,
        'target_cut': target_cut,
        'summary': f'Water availability is restored by {change * 100:.1f} percentage points: the stated {existing_cut * 100:.1f}% water cut becomes a {target_cut * 100:.1f}% target cut.',
    }


def _service_restoration_context(text, service):
    """Recognise supply restoration as the opposite of a service cut."""
    patterns = {
        'water': r'\b(increas(?:e|ing)|restore|restor(?:e|ing)|raise)\b[^.]{0,70}\b(?:available\s+)?water',
        'energy': r'\b(increas(?:e|ing)|restore|restor(?:e|ing)|raise)\b[^.]{0,70}\b(?:available\s+)?(?:energy|electricity|power)',
    }
    if service not in patterns or not re.search(patterns[service], text):
        return None
    change = _percentage(text, 0)
    label = 'water availability' if service == 'water' else 'electricity availability'
    return {
        'restoration': change,
        'summary': f'Increase household {label} by {change * 100:.1f}%. This is treated as service restoration, not a new cut.',
    }


def _support_direction(text):
    """Return -1 only for an explicit reduction in subsidy/support."""
    return -1 if re.search(r'\b(reduce|cut|withdraw|remove|decrease|lower)\b[^.]{0,60}\b(subsid(?:y|ies)|support|fare support|transport support)', text) else 1


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
    if policy_id == 'water_service_restoration':
        return {'parameter': 'water availability', 'direction': 'increase', 'value_percent': percent, 'instruction': f'Restore household water availability by {percent}%.'}
    if policy_id == 'energy_service_restoration':
        return {'parameter': 'electricity availability', 'direction': 'increase', 'value_percent': percent, 'instruction': f'Restore household electricity availability by {percent}%.'}
    if policy_id in {'public_subsidy', 'transport_subsidy'}:
        direction = 'reduce' if value < 0 else 'increase'
        label = 'public subsidy support' if policy_id == 'public_subsidy' else 'public transport subsidy'
        return {'parameter': label, 'direction': direction, 'value_percent': percent, 'instruction': f'{direction.capitalize()} {label} by {percent}%.'}
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
    value = max(-.8, min(.8, float(percentage) / 100)) if percentage is not None else default
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
    water_context = _water_restoration_context(text)
    energy_context = _service_restoration_context(text, 'energy')
    if water_context:
        selected = 'water_service_restoration'
    elif energy_context:
        selected = 'energy_service_restoration'
    elif scores[selected] == 0:
        selected = 'public_subsidy' if any(word in text for word in ('support', 'help', 'relief')) else 'water_rationing'
    matched_signals = [signal for signal in (*KEYWORDS[selected], *PHRASE_SIGNALS[selected]) if signal in text]
    policy = get_policy(selected)
    parameter_name, default = next(iter(policy['parameters'].items()))
    value = _percentage(text, default)
    if selected == 'water_service_restoration' and water_context:
        value = water_context['restoration']
    elif selected == 'energy_service_restoration' and energy_context:
        value = energy_context['restoration']
    elif selected in {'public_subsidy', 'transport_subsidy'}:
        value *= _support_direction(text)
    direction = 'reduce' if parameter_name == 'cost_change' and any(word in text for word in ('reduce', 'lower', 'affordable')) else 'increase'
    inferred_objectives = objectives or [name for name, words in OBJECTIVES.items() if any(word in text for word in words)]
    summary = water_context['summary'] if selected == 'water_service_restoration' and water_context else energy_context['summary'] if selected == 'energy_service_restoration' and energy_context else f'PolicyForge interpreted this as {policy["name"]} with {parameter_name.replace("_", " ")} set to {round(value * 100)}%, based on: {", ".join(matched_signals) or "the overall problem description"}.'
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
    energy_context = _service_restoration_context(prompt, 'energy')
    percentage = proposal["percentage"]
    summary = proposal["summary"]
    if water_context:
        proposal["policy_id"] = 'water_service_restoration'
        percentage = water_context['restoration'] * 100
        summary = water_context['summary']
    elif energy_context:
        proposal["policy_id"] = 'energy_service_restoration'
        percentage = energy_context['restoration'] * 100
        summary = energy_context['summary']
    elif proposal["policy_id"] in {'public_subsidy', 'transport_subsidy'}:
        percentage *= _support_direction(prompt)
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
    # Keep recommendations relevant to the policy area the user described.
    # Alternatives may add one supporting policy, but cannot replace the request
    # with an unrelated domain such as rent/zoning.
    if config.policy_id in POLICIES:
        policy_sets = [policy_set for policy_set in policy_sets if config.policy_id in policy_set]
    for policy_ids in policy_sets:
        selections, implementations, names = [], [], []
        for policy_id in policy_ids:
            policy = POLICIES[policy_id]
            parameter_name, default_value = next(iter(policy['parameters'].items()))
            # Preserve the user's interpreted direction and amount for the
            # focal policy; only supporting options use their neutral defaults.
            value = config.policy_parameters.get(parameter_name, default_value) if policy_id == config.policy_id else default_value
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


ADVICE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'catalog_fit': {'type': 'string', 'enum': ['supported', 'partially_supported', 'outside_catalog']},
        'summary': {'type': 'string'},
        'recommendations': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'action': {'type': 'string'}, 'detail': {'type': 'string'}, 'rationale': {'type': 'string'}, 'safeguard': {'type': 'string'},
        }, 'required': ['action', 'detail', 'rationale', 'safeguard']}},
    },
    'required': ['title', 'catalog_fit', 'summary', 'recommendations'],
}


def _advice_catalog_fit(prompt):
    score = max(_policy_scores(prompt.lower()).values(), default=0)
    return 'supported' if score >= 3 else 'partially_supported' if score else 'outside_catalog'


def _advice_template(prompt, objectives):
    """Safe, clearly non-simulated fallback policy advice."""
    text = prompt.lower()
    if any(word in text for word in ('water', 'drainage', 'flood', 'sewer')):
        title = 'Water-service and resilience advice'
        rows = [
            ('Measure the service gap first', 'Publish a ward-level baseline for supply hours, pressure, quality complaints, and unmet demand.', 'It separates a distribution problem from a total-supply problem.', 'Use aggregated data and protect household privacy.'),
            ('Prioritise vulnerable households during disruption', 'Use a time-bound contingency plan with a stated drinking-water service standard and grievance route.', 'Uniform cuts can affect households with less storage and fewer alternatives more severely.', 'Define eligibility, communication, and review before rollout.'),
            ('Reduce losses before new recurring commitments', 'Sequence leak detection, pressure management, and repair verification before expanding permanent subsidies.', 'It can improve delivered service while protecting available funds.', 'Treat savings as estimates until measured after implementation.'),
        ]
    elif any(word in text for word in ('rent', 'housing', 'tenant', 'homeless')):
        title = 'Housing affordability advice'
        rows = [
            ('Map rent pressure and displacement risk', 'Use transparent, aggregated indicators for rent burden, eviction risk, and access to work and services.', 'It helps direct support where pressure is greatest.', 'Do not publish household-level risk labels.'),
            ('Use phased, targeted relief', 'Start with time-limited support or protections for defined high-risk groups, then review before widening.', 'Phasing limits fiscal exposure and permits correction.', 'Specify an end date, appeal process, and funding source.'),
            ('Pair affordability with supply delivery', 'Coordinate rental supply, serviced land, permitting, and transport access.', 'Price action alone can shift pressure elsewhere.', 'Track displacement and availability alongside rents.'),
        ]
    elif any(word in text for word in ('solid waste', 'garbage', 'segregation', 'waste collection', 'dumping')):
        title = 'Solid-waste service design advice'
        rows = [
            ('Define the service standard', 'Set collection frequency, segregation expectations, missed-pickup handling, and accountable service areas before changing operations.', 'A clear standard makes performance measurable.', 'Avoid punitive enforcement until access to bins, collection, and information is reliable.'),
            ('Pilot ward-level operational changes', 'Test route design, collection timing, material handling, and resident communication in a small set of wards.', 'Pilots identify delivery constraints before citywide rollout.', 'Track worker safety, inclusion of informal workers, and missed-service complaints.'),
            ('Create feedback and verification loops', 'Provide an accessible complaint route and independently review service completion and disposal practices.', 'Visible feedback improves correction and trust.', 'Do not treat app reports alone as representative of households without smartphones.'),
        ]
    elif any(word in text for word in ('traffic', 'transport', 'bus', 'metro', 'mobility')):
        title = 'Accessible mobility advice'
        rows = [
            ('Identify essential-trip gaps', 'Review waiting time, affordability, first/last-mile access, and safety for essential journeys.', 'It targets access rather than average ridership alone.', 'Include women, disabled people, shift workers, and low-income users.'),
            ('Pilot a targeted fare or service change', 'Limit the first intervention to a corridor, group, or time window with measurable access outcomes.', 'A pilot creates evidence before recurring expenditure is committed.', 'Publish eligibility and funding rules.'),
            ('Coordinate fares with reliability', 'Assess service frequency, transfers, safety, and first/last-mile links together.', 'A lower fare cannot solve an inaccessible journey by itself.', 'Do not cut essential services without an equity review.'),
        ]
    else:
        title = 'Chennai policy-design advice'
        rows = [
            ('Define the problem and affected groups', 'State the service, geography, affected population, baseline, and decision within municipal control.', 'It prevents treating a symptom as the policy target.', 'Separate observed facts from assumptions.'),
            ('Design a measurable pilot', 'Specify the intervention, target group, budget ceiling, timeline, mechanism, and success measures.', 'A staged pilot creates evidence before a citywide commitment.', 'Include an exit or revision decision point.'),
            ('Make equity and funding trade-offs explicit', 'Review potential effects on low-, middle-, and high-income groups and document the funding source.', 'Trade-offs should be reviewed rather than inferred by a model.', 'Do not describe the advice as a forecast or simulation output.'),
        ]
    return {
        'title': title, 'catalog_fit': _advice_catalog_fit(prompt),
        'summary': 'This is a policy-design brief, separate from PolicyForge simulation results. Review it with local administrators, affected communities, and relevant technical specialists.',
        'recommendations': [{'action': action, 'detail': detail, 'rationale': rationale, 'safeguard': safeguard} for action, detail, rationale, safeguard in rows],
        'source': 'local_template',
        'boundary': 'Policy advice is not a simulation result, legal advice, engineering design, budget approval, or empirical prediction.',
    }


def _gemini_advice(prompt, objectives):
    model = os.getenv('GEMINI_MODEL', 'gemini-3.7-flash')
    system = (
        'You are PolicyForge’s Chennai policy-design adviser. Give practical, cautious advice for requests outside or only partly covered by the simulation catalog. '
        'Do not claim to have consulted data, laws, budgets, agencies, or community views that were not provided. Do not invent numbers, sources, outcomes, or approvals. '
        'Give exactly three actions with a concrete detail, rationale, and safeguard. Keep the advice distinct from simulation outputs. '
        f'Simulation catalog: {json.dumps({key: value["name"] for key, value in POLICIES.items()})}.'
    )
    response = httpx.post(
        'https://generativelanguage.googleapis.com/v1beta/interactions',
        headers={'x-goog-api-key': os.environ['GEMINI_API_KEY'], 'Content-Type': 'application/json'},
        json={'model': model, 'input': f'{system}\n\nPolicy question: {prompt}\nObjectives: {objectives}', 'store': False, 'response_format': {'type': 'text', 'mime_type': 'application/json', 'schema': ADVICE_SCHEMA}},
        timeout=12.0,
    )
    response.raise_for_status()
    payload = response.json()
    output = payload.get('output_text')
    if not output:
        for step in reversed(payload.get('steps', [])):
            for content in step.get('content', []):
                if content.get('type') == 'text' and content.get('text'):
                    output = content['text']
                    break
            if output:
                break
    if not output:
        raise ValueError('Gemini returned no policy advice.')
    advice = json.loads(output)
    advice['recommendations'] = advice['recommendations'][:3]
    advice['source'] = 'gemini'
    advice['boundary'] = 'AI policy advice is not a simulation result, legal advice, engineering design, budget approval, or empirical prediction.'
    return advice


def policy_advice(prompt, objectives):
    """Return advisory content that is never passed to the simulation engine."""
    if os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() == 'gemini' and os.getenv('GEMINI_API_KEY'):
        try:
            return _gemini_advice(prompt, objectives)
        except Exception:
            advice = _advice_template(prompt, objectives)
            advice['fallback_note'] = 'Gemini advice was unavailable, so a local policy-design template was used.'
            return advice
    return _advice_template(prompt, objectives)


TRIAGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'mode': {'type': 'string', 'enum': ['simulation_ready', 'needs_clarification', 'outside_catalog']},
        'matched_policy_id': {'type': 'string', 'enum': [*POLICIES, 'none']},
        'title': {'type': 'string'},
        'explanation': {'type': 'string'},
        'questions': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['mode', 'matched_policy_id', 'title', 'explanation', 'questions'],
}


def _triage_rules(prompt):
    text = prompt.lower()
    scores = _policy_scores(text)
    chosen, score = max(scores.items(), key=lambda item: item[1])
    outside_terms = ('solid waste', 'garbage', 'waste collection', 'segregation', 'air pollution', 'road safety', 'school', 'health clinic', 'crime')
    if any(term in text for term in outside_terms):
        return {
            'mode': 'outside_catalog', 'matched_policy_id': None, 'title': 'This policy is outside the current simulation catalog.',
            'explanation': 'PolicyForge does not have an evidence-labelled behavioural mechanism for this intervention, so it will not relabel it as an unrelated preset policy.',
            'questions': ['What outcome should change, and for whom?', 'Which Chennai wards or areas are in scope?', 'What delivery mechanism, budget source, and implementation period are proposed?'],
        }
    if score >= 3:
        return {
            'mode': 'simulation_ready', 'matched_policy_id': chosen, 'title': 'This request can be represented by the current simulation catalog.',
            'explanation': 'A supported policy mechanism was identified. You can review it before running a synthetic simulation.',
            'questions': [],
        }
    return {
        'mode': 'needs_clarification', 'matched_policy_id': chosen if score else None, 'title': 'More policy-design detail is needed before simulation.',
        'explanation': 'The request overlaps with a service area, but it does not yet define a supported intervention and its direction or magnitude clearly enough for a responsible simulation.',
        'questions': ['What exactly will change: service availability, household cost, subsidy, or another mechanism?', 'By how much, for how long, and which groups or wards are targeted?', 'What constraint or trade-off should be protected?'],
    }


def _triage_with_gemini(prompt):
    model = os.getenv('GEMINI_MODEL', 'gemini-3.7-flash')
    system = (
        'You are the PolicyForge triage layer. Decide whether a Chennai policy request can be honestly simulated using the existing catalog. '
        'Do not force an unrelated request into a catalog policy. Use simulation_ready only if the user clearly requests a supported mechanism and amount/direction. '
        'Use needs_clarification if it is related but mechanism, magnitude, target, or constraint is missing. Use outside_catalog for a genuinely different intervention. '
        f'Catalog: {json.dumps({key: value["name"] for key, value in POLICIES.items()})}. '
        'Return up to three short questions only when clarification is needed. Do not make empirical claims.'
    )
    response = httpx.post(
        'https://generativelanguage.googleapis.com/v1beta/interactions',
        headers={'x-goog-api-key': os.environ['GEMINI_API_KEY'], 'Content-Type': 'application/json'},
        json={'model': model, 'input': f'{system}\n\nPolicy request: {prompt}', 'store': False, 'response_format': {'type': 'text', 'mime_type': 'application/json', 'schema': TRIAGE_SCHEMA}},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    output = payload.get('output_text')
    if not output:
        for step in reversed(payload.get('steps', [])):
            for content in step.get('content', []):
                if content.get('type') == 'text' and content.get('text'):
                    output = content['text']
                    break
            if output:
                break
    if not output:
        raise ValueError('Gemini returned no planner triage.')
    result = json.loads(output)
    policy_id = result.get('matched_policy_id')
    if policy_id not in POLICIES:
        policy_id = None
    if result.get('mode') == 'simulation_ready' and not policy_id:
        result['mode'] = 'needs_clarification'
        result['questions'] = ['Which supported service mechanism should be modelled?', 'What direction and percentage change should be tested?']
    result['matched_policy_id'] = policy_id
    result['questions'] = result.get('questions', [])[:3]
    return result


def triage_policy(prompt):
    """Classify before planning so outside requests are never silently mislabelled."""
    if os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() == 'gemini' and os.getenv('GEMINI_API_KEY'):
        try:
            return _triage_with_gemini(prompt)
        except Exception:
            result = _triage_rules(prompt)
            result['fallback_note'] = 'Gemini triage was unavailable, so PolicyForge used local catalog matching.'
            return result
    return _triage_rules(prompt)
