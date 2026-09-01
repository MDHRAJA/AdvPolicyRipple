import pytest

from app.services import ai_policy


@pytest.mark.parametrize(
    ('prompt', 'expected_fragment'),
    [
        ('Vandalur infrastructure development under 2 crores.', '2 crores'),
        ('Set a ₹25 lakh ceiling for the pilot.', '₹25 lakh'),
        ('Keep the programme within INR 65,00,000.', 'INR 65,00,000'),
        ('The city can spend 65 lakhs and no more.', '65 lakhs'),
    ],
)
def test_fiscal_consideration_recognises_indian_budget_amounts(prompt, expected_fragment):
    consideration = ai_policy._fiscal_consideration(prompt)

    assert consideration is not None
    assert expected_fragment in consideration
    assert 'policy-design constraint' in consideration


@pytest.mark.parametrize(
    'prompt',
    [
        'This will be a heavy cost for the city.',
        'Use a strict cost ceiling while planning delivery.',
        'Funding must be protected during implementation.',
    ],
)
def test_fiscal_consideration_recognises_unnumbered_cost_concerns(prompt):
    assert ai_policy._fiscal_consideration(prompt) is not None


def test_fiscal_consideration_is_absent_without_money_language():
    assert ai_policy._fiscal_consideration('Improve safe pedestrian crossings near schools.') is None


def test_triage_carries_budget_constraint_for_outside_catalog_route(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_AI_MODE', 'rule_based')

    result = ai_policy.triage_policy('Create a Vandalur solid-waste infrastructure programme under 2 crores.')

    assert result['mode'] == 'outside_catalog'
    assert result['fiscal_consideration'] is not None
    assert '2 crores' in result['fiscal_consideration']


def test_water_availability_restoration_is_not_misread_as_a_water_cut(monkeypatch):
    monkeypatch.setenv('POLICYFORGE_AI_MODE', 'rule_based')

    plan = ai_policy.interpret(
        'The current water cut is 15%. Increase available water resources by 15%.',
        ['improve_access'],
    )

    assert plan['proposed_config']['policy_id'] == 'water_service_restoration'
    assert plan['proposed_config']['policy_parameters']['restoration'] == 0.15
    assert 'becomes a 0.0% target cut' in plan['interpretation'].lower()
