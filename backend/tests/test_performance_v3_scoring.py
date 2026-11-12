from decimal import Decimal

import pytest
from fastapi import HTTPException

from utils import performance_v3_scoring as scoring


def test_documented_final_score_uses_fixed_weights_and_half_up_rounding():
    assert scoring.final(1.55, 1.80, 1.20) == 1.56
    assert scoring.rounded(Decimal('1.565')) == 1.57
    assert scoring.placement(1.55, 1.80) == 'Core_Contributor'


@pytest.mark.parametrize('direction,target,actual,expected', [
    ('Higher', 100, 100, 1), ('Higher', 100, 80, 2),
    ('Higher', 100, 0, 3), ('Higher', 100, 150, 1),
    ('Lower', 10, 20, 3), ('Lower', 10, 10, 1),
    ('Binary', None, True, 1), ('Binary', None, False, 3),
    ('Rated', None, 1.75, 1.75),
])
def test_kpi_scoring_rules(direction, target, actual, expected):
    assert scoring.kpi_score({'direction': direction, 'target_value': target}, actual) == expected


@pytest.mark.parametrize('value', [True, None, float('nan'), float('inf'), 'NaN', -1])
def test_invalid_numeric_inputs_fail_closed(value):
    with pytest.raises(HTTPException): scoring.number(value)


def test_zero_target_and_lower_zero_actual_require_policy_clarification():
    for target, actual in [(0, 10), (10, 0)]:
        with pytest.raises(HTTPException):
            scoring.kpi_score({'direction': 'Lower', 'target_value': target}, actual)


def test_section_a_preserves_approved_group_blend():
    goals = [
        {'id': 'finance', 'group': 'Finance', 'weight': 100, 'direction': 'Rated'},
        {'id': 'operations', 'group': 'Operations', 'weight': 100, 'direction': 'Rated'},
    ]
    assert scoring.section_a(goals, {'finance': 1, 'operations': 3}, {'Finance': 75, 'Operations': 25})['score'] == 1.5
    with pytest.raises(HTTPException): scoring.section_a(goals, {'finance': 1, 'operations': 3})
    with pytest.raises(HTTPException): scoring.section_a(goals + [goals[0]], {'finance': 1, 'operations': 3})


def test_peer_minimum_shape_conversion_and_gap_flags():
    peers = [{'scores': [8, 10, 6, 9, 8], 'retain': 5} for _ in range(3)]
    with pytest.raises(HTTPException): scoring.section_b(peers[:2], [10] * 5)
    result = scoring.section_b(peers, [10] * 5)
    assert result['score'] == 1.9
    assert result['flagged'] == [False, False, True, False, False]
    assert result['retention_average'] == 5
    with pytest.raises(HTTPException): scoring.section_b(peers, [10])
    with pytest.raises(HTTPException): scoring.section_b([{'scores': [8], 'retain': 5}] * 3, [10] * 5)
    with pytest.raises(HTTPException): scoring.section_b([{'scores': [8] * 5, 'retain': 7}] * 3, [10] * 5)


def test_company_feedback_is_separate_and_negative_nps_scores_three():
    assert scoring.section_c(50, 4.7) == 1
    assert scoring.section_c(-1, 4.7) == 2


@pytest.mark.parametrize('a,b,expected', [
    (1, 1, 'Stars'), (1, 1.5, 'Core_Contributor'), (1, 2, 'Culture_Risk'),
    (1.5, 1, 'Core_Contributor'), (1.5, 2, 'Culture_Risk'),
    (2, 1, 'Realignment_Needed'), (2, 2, 'Exit_Track'),
])
def test_nine_box_boundaries(a, b, expected):
    assert scoring.placement(a, b) == expected
