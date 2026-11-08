"""Reproducible zero-network experiments; NOT results from Ollama model weights.

Usage (from the project root):
  python -m scripts.offline_strategy_experiment
or:
  python -m scripts.offline_strategy_experiment
"""
from backend.cube import MOVES, apply_move, correct_facelets, is_solved
from backend.guidance import optimal_next_moves
from backend.runner import build_puzzles


def simulate(trials=100, limit=20):
    naive = heuristic = guided = 0
    naive_turns, heuristic_turns, guided_turns = [], [], []
    for seed in range(trials):
        p = build_puzzles('primary', 1, seed, None)[0]
        start = p['state']
        # Control experiment: a broken model selecting U endlessly.
        state = start
        for k in range(1, limit + 1):
            state = apply_move(state, 'U')
            if is_solved(state):
                naive += 1; naive_turns.append(k); break
        # One-step heuristic only: maximize stickers matching goal. NO solver.
        state = start
        for k in range(1, limit + 1):
            chosen = max(MOVES, key=lambda move: correct_facelets(apply_move(state, move)))
            state = apply_move(state, chosen)
            if is_solved(state):
                heuristic += 1; heuristic_turns.append(k); break
        # Solver-assisted control: a proof of guarantee, NOT a model benchmark.
        state = start
        for dist in (3, 2, 1):
            state = apply_move(state, optimal_next_moves(state, dist)[0])
        if is_solved(state):
            guided += 1; guided_turns.append(3)
    return {'puzzles': trials, 'always_U_control': naive,
            'sticker_heuristic': heuristic, 'exact_solver_assisted': guided,
            'heuristic_mean_moves_on_solves':
                round(sum(heuristic_turns) / len(heuristic_turns), 2) if heuristic_turns else None}


if __name__ == '__main__':
    import json
    print('OFFLINE CUBE ENGINE EXPERIMENT -- NOT OLLAMA MODEL RESULTS')
    print(json.dumps(simulate(), indent=2))
