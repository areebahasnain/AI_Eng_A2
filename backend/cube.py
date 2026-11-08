"""Deterministic 3x3 Rubik's Cube engine.

State representation
--------------------
A cube state is a 54-character *facelet string* in Kociemba order: the six
faces U, R, F, D, L, B (nine facelets each), each face read row by row as seen
looking directly at that face from outside the cube.  Every character is the
letter of the face whose colour is on that sticker, so the solved cube is::

    UUUUUUUUU RRRRRRRRR FFFFFFFFF DDDDDDDDD LLLLLLLLL BBBBBBBBB

Orientation of each face grid (row 0 / column 0 are the top row / left column):

    U: top row touches B, left column touches L
    R: top row touches U, left column touches F
    F: top row touches U, left column touches L
    D: top row touches F, left column touches L
    L: top row touches U, left column touches B
    B: top row touches U, left column touches R

Move set and metric
-------------------
18 moves: each of U R F D L B as a clockwise quarter turn (``R``), a
counter-clockwise quarter turn (``R'``) or a half turn (``R2``), where
"clockwise" means clockwise when looking at that face from outside.  Every move
costs 1 (the *face-turn metric*, HTM).  This is the metric used for the
shortest-solution reference and for the optimality gap.

Moves are derived from a 3-D sticker model (position + normal vector) rather
than hand-typed permutation tables, so they are correct by construction; the
test-suite also checks known group identities.
"""
from __future__ import annotations

import random
from operator import itemgetter
from typing import Iterable, Sequence

FACES = "URFDLB"
SOLVED = "".join(face * 9 for face in FACES)
MOVES: tuple[str, ...] = tuple(f + s for f in FACES for s in ("", "'", "2"))
MOVE_SET = frozenset(MOVES)
OPPOSITE = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}
CENTER_INDEXES = tuple(i * 9 + 4 for i in range(6))

# Outward normal of each face in a right-handed frame: x right, y up, z towards viewer.
_NORMAL = {
    "U": (0, 1, 0),
    "R": (1, 0, 0),
    "F": (0, 0, 1),
    "D": (0, -1, 0),
    "L": (-1, 0, 0),
    "B": (0, 0, -1),
}


def _facelet_geometry() -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    """For each facelet index: (cubie position in {-1,0,1}^3, outward normal)."""
    geo = []
    for face in FACES:
        for i in range(3):  # row
            for j in range(3):  # column
                if face == "U":
                    pos = (j - 1, 1, i - 1)
                elif face == "R":
                    pos = (1, 1 - i, 1 - j)
                elif face == "F":
                    pos = (j - 1, 1 - i, 1)
                elif face == "D":
                    pos = (j - 1, -1, 1 - i)
                elif face == "L":
                    pos = (-1, 1 - i, j - 1)
                else:  # B
                    pos = (1 - j, 1 - i, -1)
                geo.append((pos, _NORMAL[face]))
    return tuple(geo)


GEOMETRY = _facelet_geometry()
_INDEX = {g: k for k, g in enumerate(GEOMETRY)}


def _rotate(axis: int, quarter_turns: int, v: tuple[int, int, int]) -> tuple[int, int, int]:
    """Rotate vector ``v`` by ``quarter_turns`` x (+90 degrees) about +axis (right-hand rule)."""
    x, y, z = v
    for _ in range(quarter_turns % 4):
        if axis == 0:
            x, y, z = x, -z, y
        elif axis == 1:
            x, y, z = z, y, -x
        else:
            x, y, z = -y, x, z
    return (x, y, z)


def _build_permutation(face: str, times: int) -> tuple[int, ...]:
    """perm[dest] = src, i.e. new_state[dest] = old_state[perm[dest]]."""
    normal = _NORMAL[face]
    axis = next(a for a in range(3) if normal[a] != 0)
    sign = normal[axis]
    # Clockwise seen from outside the face == -90 degrees about the outward normal.
    # About +axis that is 3 quarter turns when the normal is +axis, otherwise 1.
    q = 3 if sign > 0 else 1
    perm = list(range(54))
    for src, (pos, nrm) in enumerate(GEOMETRY):
        if pos[axis] != sign:
            continue
        p, n = pos, nrm
        for _ in range(times):
            p = _rotate(axis, q, p)
            n = _rotate(axis, q, n)
        perm[_INDEX[(p, n)]] = src
    return tuple(perm)


PERMUTATIONS: dict[str, tuple[int, ...]] = {}
for _face in FACES:
    PERMUTATIONS[_face] = _build_permutation(_face, 1)
    PERMUTATIONS[_face + "'"] = _build_permutation(_face, 3)
    PERMUTATIONS[_face + "2"] = _build_permutation(_face, 2)

# C-speed applicators: GETTERS[move](state) -> tuple of the new state's characters.
GETTERS = {m: itemgetter(*p) for m, p in PERMUTATIONS.items()}


def is_valid_move(move: object) -> bool:
    return isinstance(move, str) and move in MOVE_SET


def inverse_move(move: str) -> str:
    if move not in MOVE_SET:
        raise ValueError(f"Illegal move: {move!r}")
    if move.endswith("2"):
        return move
    if move.endswith("'"):
        return move[0]
    return move + "'"


def parse_algorithm(text: str) -> list[str]:
    """Split ``"R U R' U2"`` into validated moves (strict notation)."""
    moves = text.split()
    for m in moves:
        if m not in MOVE_SET:
            raise ValueError(f"Illegal move in algorithm: {m!r}")
    return moves


def invert_algorithm(moves: Sequence[str]) -> list[str]:
    return [inverse_move(m) for m in reversed(moves)]


def validate_state(state: str) -> None:
    """Raise ValueError unless ``state`` is a well-formed facelet string."""
    if not isinstance(state, str) or len(state) != 54:
        raise ValueError("State must be a 54-character string")
    for face in FACES:
        if state.count(face) != 9:
            raise ValueError(f"State must contain exactly 9 '{face}' facelets")
    for idx, face in zip(CENTER_INDEXES, FACES):
        if state[idx] != face:
            raise ValueError("Center facelets must be U R F D L B (cube is never re-oriented)")


def apply_move(state: str, move: str) -> str:
    if move not in MOVE_SET:
        raise ValueError(f"Illegal move: {move!r}")
    return "".join(GETTERS[move](state))


def apply_moves(state: str, moves: Iterable[str] | str) -> str:
    if isinstance(moves, str):
        moves = parse_algorithm(moves)
    for m in moves:
        state = apply_move(state, m)
    return state


def faces_solved(state: str) -> dict[str, bool]:
    """Per-face solved flags (a face is solved when all nine stickers match)."""
    return {
        face: state[i * 9 : i * 9 + 9] == face * 9 for i, face in enumerate(FACES)
    }


def is_solved(state: str) -> bool:
    """True when all six faces are solved."""
    return all(faces_solved(state).values())


def correct_facelets(state: str) -> int:
    """Number of facelets (0-54) already matching the solved cube (progress indicator)."""
    return sum(a == b for a, b in zip(state, SOLVED))


def generate_scramble(length: int, rng: random.Random) -> list[str]:
    """Random scramble of ``length`` moves with no trivially redundant sequences.

    No two consecutive moves turn the same face, and no ``X Y X`` pattern with Y
    on the opposite face (which would just merge into a shorter sequence).
    """
    if length < 1:
        raise ValueError("Scramble length must be >= 1")
    seq: list[str] = []
    while len(seq) < length:
        move = rng.choice(MOVES)
        face = move[0]
        if seq and seq[-1][0] == face:
            continue
        if len(seq) >= 2 and seq[-2][0] == face and OPPOSITE[face] == seq[-1][0]:
            continue
        seq.append(move)
    return seq


def scramble_state(moves: Sequence[str]) -> str:
    return apply_moves(SOLVED, moves)
