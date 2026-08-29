from app.core.models import SimulationConfig

POLICIES = {
    'water_rationing': {
        'id': 'water_rationing',
        'name': 'Water Rationing',
        'description': 'Reduce household water availability during constrained periods.',
        'policy_type': 'resource_reduction',
        'parameters': {'reduction': .25},
    },
    'water_service_restoration': {
        'id': 'water_service_restoration',
        'name': 'Water Service Restoration',
        'description': 'Restore household water availability after a shortage or rationing period.',
        'policy_type': 'water_restoration',
        'parameters': {'restoration': .15},
    },
    'rent_zoning': {
        'id': 'rent_zoning',
        'name': 'Rent / Zoning Change',
        'description': 'Model a housing cost and availability change.',
        'policy_type': 'housing',
        'parameters': {'cost_change': -.15},
    },
    'public_subsidy': {
        'id': 'public_subsidy',
        'name': 'Public Subsidy Change',
        'description': 'Increase disposable resources for targeted households.',
        'policy_type': 'subsidy',
        'parameters': {'subsidy': .20},
    },
    'energy_rationing': {
        'id': 'energy_rationing',
        'name': 'Energy Rationing',
        'description': 'Reduce energy resource availability under scarcity.',
        'policy_type': 'resource_reduction',
        'parameters': {'reduction': .20},
    },
    'transport_subsidy': {
        'id': 'transport_subsidy',
        'name': 'Public Transport Subsidy',
        'description': 'Reduce mobility costs and increase access.',
        'policy_type': 'subsidy',
        'parameters': {'subsidy': .15},
    },
}

def list_policies():
    return list(POLICIES.values())

def get_policy(pid, overrides=None):
    policy = POLICIES[pid]
    return {**policy, 'parameters': {**policy['parameters'], **(overrides or {})}}
