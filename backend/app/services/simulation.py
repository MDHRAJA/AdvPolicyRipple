import random
import statistics

from app.services.observed_data import chennai_calibration_anchor
from app.services.policies import get_policy

PRESETS = {
    'balanced': {'name': 'Balanced City', 'income': [.25, .45, .30], 'trust': (.35, .80), 'resources': (.55, .95)},
    'unequal': {'name': 'Unequal City', 'income': [.50, .35, .15], 'trust': (.20, .70), 'resources': (.30, .95)},
    'dense': {'name': 'High-Density City', 'income': [.35, .45, .20], 'trust': (.30, .75), 'resources': (.45, .85)},
    'chennai_census_2011': {'name': 'Chennai — Census 2011 anchored synthetic sample', 'income': [.25, .45, .30], 'trust': (.35, .80), 'resources': (.55, .95), 'observed_context': True},
}

def clip(value):
    return max(0, min(1, value))

def gini(values):
    values = sorted(max(0, value) for value in values)
    count = len(values)
    total = sum(values)
    return 0 if not values or not total else sum((2 * index - count - 1) * value for index, value in enumerate(values, 1)) / (count * total)

def population(config, seed):
    rng = random.Random(seed)
    preset = PRESETS[config.preset]
    agents = []
    for index in range(config.size):
        income = rng.choices(['low', 'middle', 'high'], preset['income'])[0]
        resource = rng.uniform(*preset['resources']) * (.78 if income == 'low' else 1.08 if income == 'high' else 1)
        resource = clip(resource)
        stress = clip(1 - resource + rng.gauss(0, .08))
        agents.append({
            'id': index, 'income_band': income, 'age_group': rng.choice(['18-29', '30-44', '45-64', '65+']),
            'neighborhood': rng.randrange(config.neighborhoods), 'resource_access': resource,
            'trust': rng.uniform(*preset['trust']), 'risk': rng.random(), 'cooperation': rng.betavariate(3, 2),
            'support': .5, 'satisfaction': .55, 'stress': stress, 'relocated': False, 'social_signal': 0, 'ward': str(rng.randint(1, 200)) if config.preset == 'chennai_census_2011' else None,
        })
    return agents

def metrics(agents):
    count = max(1, len(agents))
    return {
        'resource_access': statistics.fmean(agent['resource_access'] for agent in agents),
        'inequality': gini([agent['resource_access'] for agent in agents]),
        'stress': statistics.fmean(agent['stress'] for agent in agents),
        'satisfaction': statistics.fmean(agent['satisfaction'] for agent in agents),
        'policy_support': statistics.fmean(agent['support'] for agent in agents),
        'compliance': statistics.fmean((1 - agent['risk'] * .35) if agent['support'] >= .35 else .35 for agent in agents),
        'trust': statistics.fmean(agent['trust'] for agent in agents),
        'relocation': sum(agent['relocated'] for agent in agents) / count,
        'cooperation': statistics.fmean(agent['cooperation'] for agent in agents),
    }


def income_group_metrics(agents):
    """Return the same core indicators for each synthetic income segment."""
    groups = {}
    for income_band in ('low', 'middle', 'high'):
        members = [agent for agent in agents if agent['income_band'] == income_band]
        groups[income_band] = {
            'resource_access': statistics.fmean(agent['resource_access'] for agent in members),
            'stress': statistics.fmean(agent['stress'] for agent in members),
            'trust': statistics.fmean(agent['trust'] for agent in members),
            'compliance': statistics.fmean((1 - agent['risk'] * .35) if agent['support'] >= .35 else .35 for agent in members),
        }
    return groups


def income_group_impacts(baseline, final):
    return {
        income_band: {
            'baseline': baseline[income_band],
            'final': final[income_band],
            'change': {metric: round(final[income_band][metric] - baseline[income_band][metric], 4) for metric in final[income_band]},
        }
        for income_band in baseline
    }


def ward_metrics(agents):
    groups = {}
    for agent in agents:
        if agent['ward'] is not None:
            groups.setdefault(agent['ward'], []).append(agent)
    return {
        ward: {
            'resource_access': statistics.fmean(agent['resource_access'] for agent in members),
            'stress': statistics.fmean(agent['stress'] for agent in members),
            'trust': statistics.fmean(agent['trust'] for agent in members),
            'compliance': statistics.fmean((1 - agent['risk'] * .35) if agent['support'] >= .35 else .35 for agent in members),
            'synthetic_agents': len(members),
        }
        for ward, members in groups.items()
    }


def ward_impacts(baseline, final):
    return {
        ward: {
            'baseline': baseline[ward],
            'final': final[ward],
            'change': {metric: round(final[ward][metric] - baseline[ward][metric], 4) for metric in ('resource_access', 'stress', 'trust', 'compliance')},
        }
        for ward in baseline
    }


def active_policies(config):
    selections = config.policy_bundle or [{'policy_id': config.policy_id, 'policy_parameters': config.policy_parameters}]
    return [get_policy(selection['policy_id'] if isinstance(selection, dict) else selection.policy_id, selection['policy_parameters'] if isinstance(selection, dict) else selection.policy_parameters) for selection in selections]

def apply_policy(agent, policy):
    parameters = policy['parameters']
    policy_type = policy['policy_type']
    fairness = 0
    if policy_type == 'resource_reduction':
        reduction = max(0, min(.8, parameters.get('reduction', .2)))
        agent['resource_access'] = max(.02, agent['resource_access'] * (1 - reduction))
        agent['stress'] = clip(agent['stress'] + reduction * (.52 if agent['income_band'] == 'low' else .38))
        agent['satisfaction'] = clip(agent['satisfaction'] - reduction * .30)
        fairness = -reduction * (1.15 if agent['income_band'] == 'low' else .8)
    elif policy_type == 'subsidy':
        subsidy = max(0, min(.6, parameters.get('subsidy', .15)))
        targeting = 1.18 if agent['income_band'] == 'low' else .92 if agent['income_band'] == 'high' else 1
        agent['resource_access'] = clip(agent['resource_access'] + subsidy * .55 * targeting)
        agent['stress'] = clip(agent['stress'] - subsidy * .30 * targeting)
        agent['satisfaction'] = clip(agent['satisfaction'] + subsidy * .22 * targeting)
        fairness = subsidy * (.9 if agent['income_band'] == 'low' else .6)
    elif policy_type == 'housing':
        cost_change = parameters.get('cost_change', -.1)
        agent['resource_access'] = clip(agent['resource_access'] - cost_change * .25)
        agent['stress'] = clip(agent['stress'] + cost_change * .35)
        agent['satisfaction'] = clip(agent['satisfaction'] - cost_change * .18)
        fairness = -cost_change * (.9 if agent['income_band'] == 'low' else .55)
    elif policy_type == 'community_investment':
        investment = max(0, min(.5, parameters.get('investment', .15)))
        targeting = 1.15 if agent['income_band'] == 'low' else 1
        agent['resource_access'] = clip(agent['resource_access'] + investment * .34 * targeting)
        agent['stress'] = clip(agent['stress'] - investment * .22)
        agent['satisfaction'] = clip(agent['satisfaction'] + investment * .18)
        fairness = investment * .85
        agent['social_signal'] += investment * .22
    elif policy_type == 'civic_engagement':
        participation = max(0, min(.5, parameters.get('participation', .2)))
        agent['satisfaction'] = clip(agent['satisfaction'] + participation * .10)
        agent['support'] = clip(agent['support'] + participation * .16)
        fairness = participation * .95
        agent['social_signal'] += participation * .30
    return fairness

def run(config):
    rng = random.Random(config.seed)
    agents = population(config.population, config.seed)
    baseline = metrics(agents)
    baseline_income_groups = income_group_metrics(agents)
    baseline_wards = ward_metrics(agents) if config.population.preset == 'chennai_census_2011' else None
    policies = active_policies(config)
    target_wards = set(config.target_wards) if config.population.preset == 'chennai_census_2011' else set()
    timeline = []

    for round_number in range(1, config.rounds + 1):
        for agent in agents:
            agent['social_signal'] = 0
            fairness = sum(apply_policy(agent, policy) for policy in policies) if not target_wards or agent['ward'] in target_wards else 0
            agent['support'] = clip(agent['support'] + (agent['satisfaction'] - .5) * .05 + fairness * .045)
            agent['trust'] = clip(agent['trust'] + fairness * .035 + (agent['satisfaction'] - .5) * .012 - (agent['stress'] - .5) * .010)

        groups = {}
        for agent in agents:
            groups.setdefault(agent['neighborhood'], []).append(agent)
        for group in groups.values():
            if len(group) < 2:
                continue
            for _ in range(min(4, len(group))):
                first, second = rng.sample(group, 2)
                scarcity = max(0, .65 - (first['resource_access'] + second['resource_access']) / 2)
                shared = min(first['resource_access'] * .03, second['resource_access'] * .03) if min(first['cooperation'], second['cooperation']) > .48 else 0
                if shared:
                    first['resource_access'] = max(.01, first['resource_access'] - shared)
                    second['resource_access'] = clip(second['resource_access'] + shared)
                    first['social_signal'] += .012
                    second['social_signal'] += .018
                else:
                    first['social_signal'] -= scarcity * .025
                    second['social_signal'] -= scarcity * .025

        for agent in agents:
            agent['stress'] = clip(agent['stress'] + (.52 - agent['resource_access']) * .035 - rng.uniform(.002, .01))
            agent['satisfaction'] = clip(agent['satisfaction'] + (agent['resource_access'] - .5) * .025 - (agent['stress'] - .5) * .015)
            agent['trust'] = clip(agent['trust'] + agent['social_signal'] + (agent['support'] - .5) * .012 - max(0, .45 - agent['resource_access']) * .012)
            agent['cooperation'] = clip(agent['cooperation'] + agent['social_signal'] * .75 + (agent['trust'] - .5) * .020 + (agent['satisfaction'] - .5) * .012 - max(0, agent['stress'] - .7) * .018)
            agent['support'] = clip(agent['support'] + (agent['trust'] - .5) * .012 + (agent['cooperation'] - .5) * .008)
            if not agent['relocated'] and agent['stress'] > .83 and rng.random() < .01:
                agent['relocated'] = True
        timeline.append({'round': round_number, **metrics(agents)})

    final = metrics(agents)
    final_income_groups = income_group_metrics(agents)
    final_wards = ward_metrics(agents) if baseline_wards is not None else None
    weights = {'inequality': .22, 'stress': .22, 'relocation': .18, 'trust': .18, 'compliance': .20}
    score = max(0, min(100, 50 + 100 * sum(weights[key] * ((-1 if key == 'compliance' else 1) * (final[key] - baseline[key])) for key in weights)))
    examples = sorted(agents, key=lambda agent: agent['stress'], reverse=True)
    result = {
        'baseline': baseline, 'final': final, 'timeline': timeline,
        'income_group_impacts': income_group_impacts(baseline_income_groups, final_income_groups), 'policy_bundle': [policy['id'] for policy in policies], 'target_wards': sorted(target_wards), 'unintended_consequence_score': round(score, 2),
        'agent_examples': [{'profile': agent['income_band'] + ' / ' + agent['age_group'], 'neighborhood': agent['neighborhood'], 'resource_access': round(agent['resource_access'], 3), 'stress': round(agent['stress'], 3), 'trust': round(agent['trust'], 3), 'support': round(agent['support'], 3)} for agent in examples[:3]],
        'assumptions': ['Population attributes are SYNTHETIC DEMO DATA.', 'Trust and cooperation are synthetic behavioural state variables that respond to policy experience and local interactions.', 'Results are simulation outputs, not predictions of actual human behavior.'],
        'evidence_labels': {'baseline': 'SIMULATION RESULTS', 'final': 'SIMULATION RESULTS', 'assumptions': 'SIMULATION ASSUMPTIONS'},
    }
    if config.population.preset == 'chennai_census_2011':
        result['observed_data_anchor'] = chennai_calibration_anchor(config.population.size)
        result['ward_impacts'] = ward_impacts(baseline_wards, final_wards)
        result['ward_impact_evidence_type'] = 'SIMULATION OUTPUT'
        result['assumptions'].append('Ward assignment and ward-level policy effects are synthetic spatial allocation outputs; official GCC boundaries are used only for geography.')
    return result
