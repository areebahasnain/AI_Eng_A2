import random

from backend.cube import MOVES, SOLVED, apply_moves, generate_scramble, is_solved, scramble_state
from backend.solver import distance, shortest_path


def test_solved_state_has_distance_zero():
    assert shortest_path(SOLVED) == []
    assert distance(SOLVED) == 0


def test_single_moves_have_distance_one_in_face_turn_metric():
    for m in MOVES:
        assert distance(apply_moves(SOLVED, [m])) == 1, m


def test_double_turn_counts_as_one_move():
    assert distance(apply_moves(SOLVED, ["R", "R"])) == 1


def test_cancelling_moves_give_zero():
    assert distance(apply_moves(SOLVED, ["R", "R'"])) == 0


def test_two_independent_moves_have_distance_two():
    assert distance(apply_moves(SOLVED, ["R", "U"])) == 2


def test_path_actually_solves_and_is_not_longer_than_the_scramble():
    rng = random.Random(123)
    for length in (1, 2, 3, 4, 5, 6):
        for _ in range(6):
            scr = generate_scramble(length, rng)
            state = scramble_state(scr)
            path = shortest_path(state)
            assert path is not None
            assert len(path) <= length
            assert is_solved(apply_moves(state, path))


def test_distance_is_consistent_with_neighbours():
    # Applying one move changes the exact distance by at most 1.
    rng = random.Random(5)
    state = scramble_state(generate_scramble(5, rng))
    d = distance(state)
    for m in MOVES:
        d2 = distance(apply_moves(state, [m]))
        assert d2 is not None and abs(d - d2) <= 1


def test_known_distance_matches_brute_force_depth_counts():
    # Number of distinct states at depth <= 2 is 1 + 18 + 243 = 262.  Every one of
    # them must have the distance that brute-force enumeration says.
    seen = {SOLVED: 0}
    frontier = [SOLVED]
    for depth in (1, 2):
        nxt = []
        for s in frontier:
            for m in MOVES:
                n = apply_moves(s, [m])
                if n not in seen:
                    seen[n] = depth
                    nxt.append(n)
        frontier = nxt
    assert len(seen) == 262
    for s, d in seen.items():
        assert distance(s) == d


def test_returns_none_when_deeper_than_limit():
    state = scramble_state(generate_scramble(14, random.Random(9)))
    assert distance(state, max_depth=4) is None
