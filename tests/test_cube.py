import random

import pytest

from backend import cube
from backend.cube import (
    FACES,
    MOVES,
    SOLVED,
    apply_move,
    apply_moves,
    correct_facelets,
    faces_solved,
    generate_scramble,
    invert_algorithm,
    inverse_move,
    is_solved,
    parse_algorithm,
    scramble_state,
    validate_state,
)


def test_solved_state_is_valid_and_solved():
    assert len(SOLVED) == 54
    validate_state(SOLVED)
    assert is_solved(SOLVED)
    assert all(faces_solved(SOLVED).values())
    assert correct_facelets(SOLVED) == 54


def test_there_are_18_distinct_moves():
    assert len(MOVES) == 18
    assert len(set(MOVES)) == 18


def test_every_move_is_a_permutation_with_fixed_centers():
    for m in MOVES:
        perm = cube.PERMUTATIONS[m]
        assert sorted(perm) == list(range(54)), m
        for c in cube.CENTER_INDEXES:
            assert perm[c] == c, m


@pytest.mark.parametrize("face", list(FACES))
def test_quarter_turn_has_order_four(face):
    s = SOLVED
    for _ in range(3):
        s = apply_move(s, face)
        assert not is_solved(s)
    assert is_solved(apply_move(s, face))


@pytest.mark.parametrize("face", list(FACES))
def test_double_and_inverse_relationships(face):
    assert apply_move(SOLVED, face + "2") == apply_moves(SOLVED, [face, face])
    assert apply_move(SOLVED, face + "'") == apply_moves(SOLVED, [face] * 3)
    assert is_solved(apply_moves(SOLVED, [face, face + "'"]))


def test_inverse_move_helper():
    assert inverse_move("R") == "R'"
    assert inverse_move("R'") == "R"
    assert inverse_move("R2") == "R2"
    with pytest.raises(ValueError):
        inverse_move("X")


def test_u_move_matches_standard_definition():
    # Clockwise U (seen from above): the front top row goes to the left face,
    # left -> back, back -> right, right -> front.
    expected = (
        "UUUUUUUUU"
        "BBBRRRRRR"
        "RRRFFFFFF"
        "DDDDDDDDD"
        "FFFLLLLLL"
        "LLLBBBBBB"
    )
    assert apply_move(SOLVED, "U") == expected


def test_r_move_matches_standard_definition():
    # Clockwise R (seen from the right): front right column goes up to U,
    # U -> back (left column of B in its own grid), B -> D, D -> front.
    s = apply_move(SOLVED, "R")
    u, r, f, d, l, b = (s[i * 9 : i * 9 + 9] for i in range(6))
    assert r == "RRRRRRRRR" and l == "LLLLLLLLL"
    assert [u[2], u[5], u[8]] == ["F", "F", "F"]
    assert [b[0], b[3], b[6]] == ["U", "U", "U"]
    assert [d[2], d[5], d[8]] == ["B", "B", "B"]
    assert [f[2], f[5], f[8]] == ["D", "D", "D"]


def test_f_move_matches_standard_definition():
    # Clockwise F: U bottom row -> R left column, R -> D top row, D -> L, L -> U.
    s = apply_move(SOLVED, "F")
    u, r, f, d, l, b = (s[i * 9 : i * 9 + 9] for i in range(6))
    assert [u[6], u[7], u[8]] == ["L", "L", "L"]
    assert [r[0], r[3], r[6]] == ["U", "U", "U"]
    assert [d[0], d[1], d[2]] == ["R", "R", "R"]
    assert [l[2], l[5], l[8]] == ["D", "D", "D"]


def test_sexy_move_has_order_six():
    s = SOLVED
    for i in range(1, 7):
        s = apply_moves(s, "R U R' U'")
        assert is_solved(s) == (i == 6)


def test_t_perm_is_an_involution():
    t = "R U R' U' R' F R2 U' R' U' R U R' F'"
    once = apply_moves(SOLVED, t)
    assert not is_solved(once)
    assert is_solved(apply_moves(once, t))


def test_algorithm_followed_by_its_inverse_is_identity():
    rng = random.Random(7)
    alg = generate_scramble(20, rng)
    s = apply_moves(SOLVED, alg)
    assert is_solved(apply_moves(s, invert_algorithm(alg)))


def test_states_stay_valid_after_random_moves():
    rng = random.Random(1)
    s = SOLVED
    for _ in range(200):
        s = apply_move(s, rng.choice(MOVES))
        validate_state(s)


def test_parse_algorithm_is_strict():
    assert parse_algorithm("R U' F2") == ["R", "U'", "F2"]
    for bad in ("R3", "r", "R’", "X"):
        with pytest.raises(ValueError):
            parse_algorithm(bad)


def test_apply_move_rejects_illegal_moves():
    with pytest.raises(ValueError):
        apply_move(SOLVED, "M")


def test_validate_state_errors():
    with pytest.raises(ValueError):
        validate_state("U" * 53)
    with pytest.raises(ValueError):
        validate_state("U" * 54)
    swapped = list(SOLVED)
    swapped[4], swapped[13] = swapped[13], swapped[4]
    with pytest.raises(ValueError):
        validate_state("".join(swapped))


def test_scramble_is_deterministic_and_non_redundant():
    a = generate_scramble(15, random.Random(42))
    b = generate_scramble(15, random.Random(42))
    assert a == b and len(a) == 15
    for x, y in zip(a, a[1:]):
        assert x[0] != y[0]
    for x, y, z in zip(a, a[1:], a[2:]):
        assert not (x[0] == z[0] and cube.OPPOSITE[x[0]] == y[0])


def test_scramble_state_unsolves_the_cube():
    s = scramble_state(generate_scramble(4, random.Random(3)))
    assert not is_solved(s)
    assert correct_facelets(s) < 54
