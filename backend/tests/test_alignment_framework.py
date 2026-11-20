"""Approved framework wording, pillar mapping and unchanged 1-5 scoring."""
from routes.surveys import FTE_ALIGNMENT_QUESTIONS, calc_pillar_score
from .test_performance_v3_end_to_end import configured

EXPECTED = [{'id': 'q1', 'pillar': 1, 'text': 'My work at Solvit regularly challenges me to grow and develop my skills.'}, {'id': 'q2', 'pillar': 1, 'text': 'I am trusted to make decisions and take action without unnecessary oversight.'}, {'id': 'q3', 'pillar': 1, 'text': 'I feel genuinely appreciated for the contribution I make to this team.'}, {'id': 'q4', 'pillar': 1, 'text': 'Solvit provides a professional, effective, and growth-oriented environment.'}, {'id': 'q5', 'pillar': 2, 'text': "I consistently demonstrate Solvit's five non-negotiables in my day-to-day work."}, {'id': 'q6', 'pillar': 2, 'text': "My colleagues consistently demonstrate Solvit's five non-negotiables."}, {'id': 'q7', 'pillar': 2, 'text': 'Solvit holds people accountable when the non-negotiables are not upheld.'}, {'id': 'q8', 'pillar': 2, 'text': 'The values Solvit states publicly are the values Solvit actually lives internally.'}, {'id': 'q9', 'pillar': 3, 'text': 'My compensation is fair relative to the work I do and the results I deliver.'}, {'id': 'q10', 'pillar': 3, 'text': 'When I perform well, I am recognised for it in a meaningful and specific way.'}, {'id': 'q11', 'pillar': 3, 'text': 'The bonus and incentive structure at Solvit motivates me to perform at my best.'}, {'id': 'q12', 'pillar': 3, 'text': 'Overall, I feel valued and rewarded for my contribution to Solvit.'}]


def test_approved_framework_has_exact_wording_and_four_questions_per_pillar():
    assert FTE_ALIGNMENT_QUESTIONS == EXPECTED
    for pillar in (1, 2, 3):
        assert len([q for q in FTE_ALIGNMENT_QUESTIONS if q['pillar'] == pillar]) == 4
        assert calc_pillar_score({q['id']: 1 for q in EXPECTED}, EXPECTED, pillar) == 20
        assert calc_pillar_score({q['id']: 3 for q in EXPECTED}, EXPECTED, pillar) == 60
        assert calc_pillar_score({q['id']: 5 for q in EXPECTED}, EXPECTED, pillar) == 100


def test_new_cycle_snapshots_approved_questions():
    db, users, cycle, review = configured()
    assert db.survey_windows.docs[0]['questions'] == EXPECTED
