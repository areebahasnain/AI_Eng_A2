"""Clef regression controls: no distance oracle, no misleading scorecard by default."""
import asyncio

from backend.adapters import Decision
from backend.config import Settings, ollama_models
from backend.cube import MOVES, apply_move, correct_facelets
from backend.runner import Run, build_puzzles, play_trial
from backend.solver import shortest_path_cached


class CaptureThree:
    def __init__(self, moves):
        self.moves = list(moves)
        self.index = 0
        self.observations = []

    async def decide(self, state):
        self.observations.append(state)
        move = self.moves[self.index]
        self.index += 1
        return Decision(move, True, 0.2, 0.2, 1, 0, 0, local_requests=1)


def test_clef_previously_solved_seed_still_works_without_rewriting_moves():
    # Clef actually solved this seed in the user's saved run; here we verify
    # that the engine/action protocol still preserves that three-turn solution.
    p = build_puzzles('primary', 1, 383828, None)[0]
    solution = shortest_path_cached(p['state'], 3)
    assert len(solution) == 3
    adapter = CaptureThree(solution)
    spec = ollama_models()[0]
    settings = Settings(provider='ollama', mock=False, models=[spec],
                        time_limit_s=15, max_moves=20)
    run = Run({'suite':'primary','seed':383828,'ollama_guided':False}, settings, [spec.key])
    trial = asyncio.run(play_trial(run, p, spec.key, adapter))
    assert trial['solved'] and trial['moves_used'] == 3
    assert trial['guide_overrides'] == 0 and not trial['assisted_mode']
    assert trial['sticker_scorecard'] is False
    assert trial['progress_counts']['closer'] == 3
    for obs in adapter.observations:
        assert 'one_step_sticker_scores' not in obs
        assert 'distance_reducing_choices' not in obs
        assert 'shortest_path' not in obs
        assert 'faces_3x3' in obs
        assert 'avoid_revisit_moves' in obs


def test_recorded_failed_seed_exposes_sticker_heuristic_trap():
    # A real failure case: the old heuristic scored D2 better than D, although
    # D is a correct first solving move and D2 leaves distance unchanged.
    p = build_puzzles('primary', 1, 734383, None)[0]
    state = p['state']
    assert p['scramble'] == ["D'", 'L2', "D'"]
    assert 'D' in shortest_path_cached(state, 3)
    assert correct_facelets(apply_move(state, 'D2')) > correct_facelets(apply_move(state, 'D'))
    assert shortest_path_cached(apply_move(state, 'D2'), 2) is None
    assert shortest_path_cached(apply_move(state, 'D'), 2) is not None


def test_four_local_model_keys_have_no_deepseek():
    specs = ollama_models()
    assert [m.key for m in specs] == ['clef_local', 'qwen_local', 'llama_local', 'gemma_local']
    assert specs[2].model_id == 'llama3.2:3b'
