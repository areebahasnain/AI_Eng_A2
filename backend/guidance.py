"""Explicitly assisted LOCAL demonstrations, not unassisted model benchmarks.

When switched on by the user, an exact reference search identifies actions
which decrease the shortest cube distance. The model still proposes one legal
move; a guard may replace its choice. All replacements are exposed in logs and
marked as SOLVER-ASSISTED. No hosted/paid request ever uses this module.
"""
from __future__ import annotations

from .cube import MOVES, apply_move
from .solver import shortest_path_cached


def optimal_next_moves(state: str, distance: int) -> list[str]:
    """All moves that reduce the *proven* distance by exactly one.

    For the teacher's 3-move scrambles we evaluate only to depth 2, then 1,
    then 0; there is no expensive 7/8-move search on arbitrary states.
    """
    if not 1 <= distance <= 3:
        raise ValueError("The demo guidance works only for states at distances 1–3")
    moves = [m for m in MOVES if
             shortest_path_cached(apply_move(state, m), distance - 1) is not None]
    if not moves:
        raise RuntimeError("Reference engine could not find a distance-decreasing action")
    return moves


def choose_guided_move(proposed: str | None, candidates: list[str]) -> tuple[str, bool]:
    """Accept a model's optimal proposal or transparently substitute one.

    Replacing a proposed action makes the run solver-assisted, NOT proof that
    the model can solve the cube. Always report the raw model proposal too.
    """
    if proposed in candidates:
        return proposed, False
    return candidates[0], True
