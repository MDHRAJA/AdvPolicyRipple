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
    terms = ('budget', 'fund', 'funds', 'money', 'cost', 'afford', 'fiscal', 'spend', 'spending', 'revenue', 'allocation', 'cap')
    currency_amount = re.compile(
        r'(?:₹|rs\.?|inr)\s*\d[\d,]*(?:\.\d+)?|'
        r'\b\d[\d,]*(?:\.\d+)?\s*(?:inr|rupees?|lakh(?:s)?|lac(?:s)?|crore(?:s)?|million|thousand)\b',
        re.IGNORECASE,
    )
    sentences = [sentence.strip() for sentence in re.split(r'(?<=[.!?])\s+', text.strip()) if sentence.strip()]
    relevant = [
        sentence for sentence in sentences
        if any(term in sentence.lower() for term in terms) or currency_amount.search(sentence)
    ]
    if not relevant:
        return None
    stated_constraint = relevant[0][:360]
    return (
        f'Stated budget constraint: {stated_constraint} '
        'PolicyForge will use this as a policy-design constraint. It will not silently invent a funding cut, price, or reallocation, '
        'and it will not treat a monetary amount as a synthetic simulation parameter unless the selected policy mechanism explicitly models it.'
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
    plan = _build_plan(selected, value * 100, direction, inferred_objectives, prompt, 'rule_based', summary, _fiscal_consideration(prompt))
    plan['proposed_config']['rounds'] = rounds
    plan['proposed_config']['seed'] = seed
    return plan



class GeminiUnavailableError(RuntimeError):
    """A safe, user-facing Gemini configuration or response failure."""


def _gemini_json_for_model(system, prompt, schema, model, timeout=60.0):
    """Use one Gemini GenerateContent model and return structured JSON."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiUnavailableError("Gemini is enabled, but the backend Gemini API key is missing.")
    model = model.strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    structured_request = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    try:
        response = httpx.post(endpoint, headers=headers, json=structured_request, timeout=timeout)

        # Some Gemini projects accept API-key authentication for ordinary JSON
        # generation but reject the advanced response-schema route. Retry with
        # an equivalent JSON-only prompt rather than treating a working key as
        # unavailable. Parsed output is still validated locally by the caller.
        if response.status_code in {400, 401, 403}:
            plain_json_prompt = (
                f"{system}\n\n{prompt}\n\n"
                "Return only valid JSON that satisfies this schema:\n"
                f"{json.dumps(schema)}"
            )
            response = httpx.post(
                endpoint,
                headers=headers,
                json={
                    "contents": [{"role": "user", "parts": [{"text": plain_json_prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=timeout,
            )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as error:
        raise GeminiUnavailableError(
            "Gemini took longer than expected to prepare the structured policy response. Please try again."
        ) from error
    except httpx.HTTPStatusError as error:
        # The API error is useful for configuration diagnosis and contains no key.
        status = error.response.status_code
        try:
            detail = error.response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = ""
        message = f"Gemini request failed with HTTP {status}."
        if isinstance(detail, str) and detail.strip():
            message += f" {detail.strip()[:300]}"
        raise GeminiUnavailableError(message) from error
    except (httpx.HTTPError, ValueError) as error:
        raise GeminiUnavailableError(
            "Gemini could not respond due to a network or response-format error. Try again shortly."
        ) from error

    candidates = payload.get("candidates", [])
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    output = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not output.strip():
        raise GeminiUnavailableError("Gemini returned an empty policy response. Please try again.")
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise GeminiUnavailableError("Gemini returned an invalid policy response. Please try again.") from error


def _gemini_model_chain():
    """Return the configured Gemini-only model order without duplicate calls."""
    configured = (
        os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        os.getenv("GEMINI_FALLBACK_MODEL_1", "gemini-3.5-flash"),
        os.getenv("GEMINI_FALLBACK_MODEL_2", "gemini-3.5-flash-lite"),
        os.getenv("GEMINI_FALLBACK_MODEL_3", "gemini-3.1-flash-lite"),
    )
    models = []
    for model in configured:
        normalized = str(model or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)
    return models


def _gemini_json(system, prompt, schema, timeout=60.0):
    """Try the configured Gemini models in order with one validated contract.

    Every model receives the same prompt and schema. Callers still validate the
    parsed result locally, so a fallback can never change the PolicyForge
    response shape or bypass its simulation safeguards.
    """
    errors = []
    for model in _gemini_model_chain():
        try:
            return _gemini_json_for_model(system, prompt, schema, model, timeout=timeout)
        except GeminiUnavailableError as error:
            message = str(error)
            errors.append(f"{model}: {message}")
            # An invalid/missing credential cannot be solved by switching models.
            if "http 401" in message.lower() or "api key" in message.lower():
                raise

    attempted = ", ".join(_gemini_model_chain())
    final_detail = errors[-1] if errors else "No Gemini model was configured."
    raise GeminiUnavailableError(
        f"Gemini models were unavailable after trying: {attempted}. {final_detail}"
    )


def _interpret_gemini(prompt, objectives):
    """Interpret the request with Gemini, then validate every returned field locally."""
    system = (
        "You are the PolicyForge policy-intake layer. Select exactly one supported policy and one percentage. "
        "Never invent policies, datasets, outcomes, or evidence. Interpret only the user text. "
        f"Supported policies: {json.dumps({key: value['name'] for key, value in POLICIES.items()})}. "
        f"Allowed objectives: {sorted(VALID_OBJECTIVES)}. "
        "Use housing_direction=reduce only when the user wants housing costs reduced; otherwise use increase. "
        "A stated increase in water availability is not a new water cut. If the request gives a current water cut and an availability restoration, return the remaining target cut after subtracting the restoration. "
        "The summary must state the interpretation, not a prediction or recommendation."
    )
    proposal = _gemini_json(
        system,
        f"Policy request: {prompt}\nSelected objectives: {objectives}",
        GEMINI_SCHEMA,
    )
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
        return {"configured": "gemini", "display": "Gemini-assisted", "fallback": "Gemini policy advice is shown only when Gemini responds; unavailable advice is reported clearly."}
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
        candidates.append({'policy_id': '+'.join(policy_ids), 'name': ' + '.join(names), 'score': round(score, 4), 'preview': final, 'income_groups': outcome['income_group_impacts'], 'policy_bundle': implementations, 'implementation': implementations[0], 'result': outcome})
    candidates.sort(key=lambda item: item['score'], reverse=True)
    best = candidates[0]
    evidence = []
    if 'improve_access' in objectives: evidence.append(f"resource access {best['preview']['resource_access'] * 100:.1f}%")
    if 'reduce_stress' in objectives: evidence.append(f"stress {best['preview']['stress'] * 100:.1f}%")
    if 'reduce_inequality' in objectives: evidence.append(f"inequality {best['preview']['inequality'] * 100:.1f}%")
    if 'build_trust' in objectives: evidence.append(f"trust {best['preview']['trust'] * 100:.1f}%")
    if 'improve_compliance' in objectives: evidence.append(f"compliance {best['preview']['compliance'] * 100:.1f}%")
    # The winning run is returned so the planner can open Results without
    # re-running the identical 10,000-agent configuration. Alternatives keep
    # their compact preview shape to avoid sending unused full timelines.
    alternatives = [{key: value for key, value in candidate.items() if key != 'result'} for candidate in candidates[1:3]]
    return {'recommended': best, 'alternatives': alternatives, 'explanation': f"AI rationale: this option ranked first against {', '.join(objectives).replace('_', ' ')} after comparing individual policies and every supported two-policy bundle. Its modelled profile is {', '.join(evidence)}.", 'boundary': 'Recommendations rank synthetic simulation outputs against user-selected objectives; they are not implementation advice or empirical forecasts.'}


ADVICE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'catalog_fit': {'type': 'string', 'enum': ['supported', 'partially_supported', 'outside_catalog']},
        'summary': {'type': 'string'},
        'executive_recommendation': {'type': 'string'},
        'policy_design': {'type': 'string'},
        'targeting': {'type': 'string'},
        'budget_strategy': {'type': 'string'},
        'implementation_plan': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'phase': {'type': 'string'}, 'timeframe': {'type': 'string'}, 'action': {'type': 'string'}, 'owner': {'type': 'string'},
        }, 'required': ['phase', 'timeframe', 'action', 'owner']}},
        'success_measures': {'type': 'array', 'items': {'type': 'string'}},
        'key_tradeoffs': {'type': 'array', 'items': {'type': 'string'}},
        'decisions_required': {'type': 'array', 'items': {'type': 'string'}},
        'follow_up_questions': {'type': 'array', 'items': {'type': 'string'}},
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
    elif any(word in text for word in ('delimitation', 'boundary', 'electoral', 'administrative boundary')):
        title = 'Administrative boundary review policy'
        rows = [
            ('Adopt a service-first boundary review mandate', 'Frame the proposal around equal access to municipal services, administrative workload, and accountable representation—not merely redrawing lines.', 'A service-first mandate gives the review a clear public purpose.', 'Keep the final decision with the legally authorised body and publish the review criteria.'),
            ('Use an independent, criteria-based review panel', 'Set out transparent criteria such as population balance, community continuity, service catchments, and geographic contiguity before draft boundaries are produced.', 'Pre-agreed criteria reduce discretionary or politically selective changes.', 'Require conflict-of-interest declarations and publish all deviations from the criteria.'),
            ('Run a staged consultation and objection process', 'Release draft options, allow written objections, hold accessible ward-level hearings, and publish a response to material objections before finalisation.', 'It creates a traceable route for affected communities to challenge proposals.', 'Provide non-digital participation routes and translated or accessible materials where needed.'),
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
        'follow_up_questions': [],
        'boundary': 'Policy advice is not a simulation result, legal advice, engineering design, budget approval, or empirical prediction.',
    }


def _gemini_advice(prompt, objectives):
    system = (
        'You are a senior Chennai municipal-policy agent writing a presentation-grade policy recommendation for a request outside or only partly covered by the simulation catalog. '
        'Be decisive: propose one named policy and explain exactly how it should work. Avoid generic advice such as “assess the issue”, “consider vulnerable groups”, or “collect data” unless it directly enables a named delivery decision. '
        'Return an executive_recommendation of 2–3 sentences; a policy_design that describes the instrument, eligibility, operational mechanism and governance; targeting; a realistic budget_strategy; a three-phase implementation_plan; 3–5 success_measures; 2–4 key_tradeoffs; and 2–4 decisions_required from the sponsor. '
                'If the policy question states a budget cap, funding limit, fiscal-neutrality requirement, no-new-spending rule, revenue constraint, or specified programme to reduce, carry that exact constraint into budget_strategy, recommended actions, implementation sequence, and trade-offs. Do not invent a funding cut, price, cost, or allocation. State clearly when the constraint guides the proposal but is not a numeric PolicyForge simulation input. '
        'Give exactly three substantive recommendations. Each must name the instrument, target, implementation choice, rationale, safeguard, and a concrete implementation detail such as a threshold, sequence, operating rule, or decision point. Where the request lacks a number, location, legal authority, or budget, state one clearly labelled proposed/conditional design choice instead of inventing facts. '
        'Set follow_up_questions to an empty array unless a missing fact would materially change the proposed instrument, target, funding route, or governance. When needed, ask at most three concise, request-specific questions; never ask generic questions such as “what outcome”, “which area”, or “what budget”. The policy recommendation must remain useful without an answer. '
        'Do not claim to have consulted data, laws, budgets, agencies, or communities that were not provided. Keep this as an AI proposal, distinct from simulation outputs, and never relabel an outside policy as a catalog intervention. '
        f'Simulation catalog: {json.dumps({key: value["name"] for key, value in POLICIES.items()})}.'
    )
    advice = _gemini_json(
        system,
        f"Policy question: {prompt}\nObjectives: {objectives}",
        ADVICE_SCHEMA,
    )
    advice['recommendations'] = advice['recommendations'][:3]
    advice['source'] = 'gemini'
    advice['boundary'] = 'AI policy advice is not a simulation result, legal advice, engineering design, budget approval, or empirical prediction.'
    return advice

def _enrich_policy_advice(advice, prompt):
    """Ensure every adviser response has presentation-ready sections, including local fallback."""
    text = prompt.lower()
    title = advice.get('title', 'Chennai policy proposal')
    boundary_topic = any(word in text for word in ('delimitation', 'boundary', 'electoral'))
    default_design = (
        'Create an independent, criteria-led administrative boundary review: publish the review criteria, prepare draft options, '
        'and use a time-bound consultation and objection process before a legally authorised final decision.'
        if boundary_topic else
        'Implement the proposed intervention through a time-bound pilot, explicit eligibility and delivery rules, and a documented decision to expand, revise, or stop it.'
    )
    defaults = {
        'executive_recommendation': f'Adopt the proposed {title} as a defined, time-bound policy programme rather than a broad statement of intent. Start with the specified pilot and only scale it after the delivery, equity, and fiscal conditions below are reviewed.',
        'policy_design': default_design,
        'targeting': 'Use the geography, groups, and service users stated in the request. Where they are not specified, obtain a sponsor decision before implementation rather than assuming citywide coverage.',
        'budget_strategy': 'Set a capped pilot envelope and identify the approving budget line before launch. Treat future savings or revenue as provisional until they are evidenced after delivery.',
        'implementation_plan': [
            {'phase': '1 · Authorise and design', 'timeframe': 'Weeks 0–4', 'action': 'Approve scope, delivery rules, accountability, and the pilot budget cap.', 'owner': 'Policy sponsor and designated implementing authority'},
            {'phase': '2 · Pilot delivery', 'timeframe': 'Months 2–4', 'action': 'Run the intervention in the approved scope, publish a service standard, and resolve implementation issues.', 'owner': 'Delivery unit with ward-level coordination'},
            {'phase': '3 · Review and decide', 'timeframe': 'Month 5', 'action': 'Review outcomes, complaints, costs, and distributional effects; decide whether to scale, revise, or stop.', 'owner': 'Independent review group and policy sponsor'},
        ],
        'success_measures': ['Delivery reached the defined target group or area.', 'The stated service or administrative standard was met.', 'Cost remained within the approved pilot cap.', 'Complaints and exclusion risks were documented and resolved.'],
        'key_tradeoffs': ['A faster rollout can reduce time for consultation and implementation testing.', 'Targeting can improve equity but creates eligibility and communication complexity.'],
        'decisions_required': ['Confirm the accountable authority and legal route.', 'Confirm the target geography and beneficiary group.', 'Confirm the maximum pilot budget and the decision point for scale-up.'],
        'follow_up_questions': [],
    }
    for key, value in defaults.items():
        if not advice.get(key):
            advice[key] = value
    advice['implementation_plan'] = advice['implementation_plan'][:3]
    advice['success_measures'] = advice['success_measures'][:5]
    advice['key_tradeoffs'] = advice['key_tradeoffs'][:4]
    advice['decisions_required'] = advice['decisions_required'][:4]
    advice['follow_up_questions'] = [question for question in advice.get('follow_up_questions', []) if isinstance(question, str) and question.strip()][:3]
    return advice


def policy_advice(prompt, objectives):
    """Return advisory content that is never passed to the simulation engine.

    Gemini mode is deliberately fail-visible: generic local text must never be
    presented as an AI-generated recommendation when Gemini is unavailable.
    """
    if os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() == 'gemini':
        return _enrich_policy_advice(_gemini_advice(prompt, objectives), prompt)
    return _enrich_policy_advice(_advice_template(prompt, objectives), prompt)


SCENARIO_METRICS = (
    'resource_access', 'inequality', 'stress', 'satisfaction', 'policy_support',
    'compliance', 'trust', 'relocation', 'cooperation',
)
EXPLORATORY_SCENARIO_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'summary': {'type': 'string'},
        'assumptions': {'type': 'array', 'items': {'type': 'string'}},
        'metric_changes': {
            'type': 'object',
            'properties': {metric: {'type': 'number', 'minimum': -0.15, 'maximum': 0.15} for metric in SCENARIO_METRICS},
            'required': list(SCENARIO_METRICS),
        },
        'income_sensitivity': {
            'type': 'object',
            'properties': {
                'low': {'type': 'number', 'minimum': 0.5, 'maximum': 1.5},
                'middle': {'type': 'number', 'minimum': 0.5, 'maximum': 1.5},
                'high': {'type': 'number', 'minimum': 0.5, 'maximum': 1.5},
            },
            'required': ['low', 'middle', 'high'],
        },
    },
    'required': ['title', 'summary', 'assumptions', 'metric_changes', 'income_sensitivity'],
}


def exploratory_scenario(prompt, objectives):
    """Create transparent, bounded AI assumptions for an out-of-catalog scenario.

    This does not claim that Census data estimates the policy effect. The
    resulting profile is applied only to a Census-anchored synthetic baseline
    and is always labelled as a Census-informed synthetic scenario.
    """
    if os.getenv('POLICYFORGE_AI_MODE', 'rule_based').lower() != 'gemini':
        raise GeminiUnavailableError('Exploratory AI scenarios require Gemini to be enabled on the backend.')

    system = (
        "You are PolicyForge's exploratory-scenario designer for a Chennai policy outside the validated simulation catalog. "
        'Produce transparent modelling assumptions, not evidence or a forecast. '
        'Use small, bounded end-state changes (between -0.15 and 0.15) for each supplied synthetic metric. '
        'Positive stress, inequality, and relocation changes are adverse; positive resource access, satisfaction, policy support, '
        'compliance, trust, and cooperation changes are beneficial. '
        'Set income_sensitivity above 1 when low-income households are more exposed, below 1 when they are protected. '
        'Give 2–4 concise assumptions that make clear why the changes are hypothetical. '
        'Never claim to have observed effects, consulted Census microdata, or established causality.'
    )
    profile = _gemini_json(
        system,
        f'Policy question: {prompt}\nObjectives: {objectives}\n'
        'Return a presentation-ready exploratory scenario for a Chennai Census 2011 anchored synthetic population.',
        EXPLORATORY_SCENARIO_SCHEMA,
    )

    changes = profile.get('metric_changes', {})
    profile['metric_changes'] = {
        metric: round(max(-0.15, min(0.15, float(changes.get(metric, 0)))), 4)
        for metric in SCENARIO_METRICS
    }
    sensitivity = profile.get('income_sensitivity', {})
    profile['income_sensitivity'] = {
        group: round(max(0.5, min(1.5, float(sensitivity.get(group, 1)))), 3)
        for group in ('low', 'middle', 'high')
    }
    profile['title'] = str(profile.get('title') or 'Exploratory Chennai policy scenario')[:160]
    profile['summary'] = str(profile.get('summary') or 'AI-generated assumptions are applied to a Census-anchored synthetic Chennai baseline.')[:600]
    profile['assumptions'] = [str(item)[:300] for item in profile.get('assumptions', []) if str(item).strip()][:4]
    if not profile['assumptions']:
        profile['assumptions'] = ['This is an Census-informed synthetic scenario, not an observed-data estimate or forecast.']
    profile['evidence_type'] = 'AI ASSUMPTION-DRIVEN SCENARIO'
    profile['source'] = 'gemini'
    return profile


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
    # Explicit service changes with a percentage are simulation-ready even when
    # they do not contain a catalog label such as "rationing".
    if 'water' in text and re.search(r'\b(reduce|cut|lower|decrease)\b', text) and re.search(r'\d{1,2}(?:\.\d+)?\s*%', text):
        return {
            'mode': 'simulation_ready', 'matched_policy_id': 'water_rationing', 'title': 'This request can be represented by the current simulation catalog.',
            'explanation': 'It explicitly specifies a reduction in household water availability and a magnitude.', 'questions': [],
        }
    if 'water' in text and _water_restoration_context(text):
        return {
            'mode': 'simulation_ready', 'matched_policy_id': 'water_service_restoration', 'title': 'This request can be represented by the current simulation catalog.',
            'explanation': 'It explicitly specifies a restoration in household water availability.', 'questions': [],
        }
    if any(word in text for word in ('energy', 'electricity', 'power')) and re.search(r'\b(reduce|cut|lower|decrease)\b', text) and re.search(r'\d{1,2}(?:\.\d+)?\s*%', text):
        return {
            'mode': 'simulation_ready', 'matched_policy_id': 'energy_rationing', 'title': 'This request can be represented by the current simulation catalog.',
            'explanation': 'It explicitly specifies a reduction in electricity availability and a magnitude.', 'questions': [],
        }
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
    system = (
        'You are the PolicyForge triage layer. Decide whether a Chennai policy request can be honestly simulated using the existing catalog. '
        'Do not force an unrelated request into a catalog policy. Use simulation_ready only if the user clearly requests a supported mechanism and amount/direction. '
        'Use needs_clarification if it is related but mechanism, magnitude, target, or constraint is missing. Use outside_catalog for a genuinely different intervention. '
        f'Catalog: {json.dumps({key: value["name"] for key, value in POLICIES.items()})}. '
        'Return up to three short questions only when clarification is needed. Do not make empirical claims.'
    )
    result = _gemini_json(system, f"Policy request: {prompt}", TRIAGE_SCHEMA, timeout=45.0)
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
            result = _triage_with_gemini(prompt)
        except Exception:
            result = _triage_rules(prompt)
            result['fallback_note'] = 'Gemini triage was unavailable, so PolicyForge used local catalog matching.'
    else:
        result = _triage_rules(prompt)
    # Preserve funding constraints for every route, including outside-catalog
    # scenarios that intentionally do not create a preset simulation plan.
    result['fiscal_consideration'] = _fiscal_consideration(prompt)
    return result
