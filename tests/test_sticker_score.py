from backend.contract import OLLAMA_COMMON_GUIDE
from backend.cube import MOVES, apply_move, correct_facelets
from backend.progress import one_step_sticker_observation
from backend.runner import build_puzzles
from scripts.offline_strategy_experiment import simulate


def test_sticker_table_predicts_each_action_exactly_without_a_distance_oracle():
    original = build_puzzles('primary', 1, 18, None)[0]['state']
    report = one_step_sticker_observation(original, {original})
    assert len(report['one_step_sticker_scores']) == 18
    assert set(report['one_step_sticker_scores']) == set(MOVES)
    for move in MOVES:
        p = report['one_step_sticker_scores'][move]
        assert p == correct_facelets(apply_move(original, move))
    assert 'one_step_sticker_scores' in OLLAMA_COMMON_GUIDE


def test_offline_controls_reproduce_and_do_not_claim_model_solve_rate():
    outcomes = simulate(trials=100)
    assert outcomes['puzzles'] == 100
    assert outcomes['always_U_control'] == 0
    assert outcomes['sticker_heuristic'] == 64
    assert outcomes['exact_solver_assisted'] == 100
