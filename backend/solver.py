"""Exact shortest-solution reference for small scrambles.

A bidirectional breadth-first search (BFS) over the 18-move graph finds the
*exact* minimum number of moves (face-turn metric) needed to solve a state.
Searching from both the scrambled state and the solved cube and always
expanding the smaller frontier keeps this tiny: distances up to 8 need only
~4 levels per side (~50k states each).

Correctness of the early exit: if no state is shared between the two searches
yet, the distance exceeds ``a + b`` (levels expanded on each side).  When the
next expansion first produces a state already known to the other side, every
such candidate has length exactly ``a + b + 1``, so the first meeting is optimal.

For deep states (distance > ``max_depth``) the search returns ``None`` -
exact distance unknown - and the benchmark falls back to the scramble length
as an upper bound (clearly labelled in the UI and in the results).
"""
from __future__ import annotations

from functools import lru_cache

from .cube import GETTERS, MOVES, SOLVED, inverse_move

_SOLVED_T = tuple(SOLVED)


def _build_path(meeting, fwd, bwd) -> list[str]:
    left: list[str] = []
    s = meeting
    while fwd[s][1] is not None:
        _, parent, move = fwd[s]
        left.append(move)
        s = parent
    left.reverse()
    right: list[str] = []
    s = meeting
    while bwd[s][1] is not None:
        _, parent, move = bwd[s]
        right.append(inverse_move(move))
        s = parent
    return left + right


def shortest_path(state: str, max_depth: int = 8) -> list[str] | None:
    """One optimal solution (list of moves), or ``None`` if longer than ``max_depth``."""
    start = tuple(state)
    if start == _SOLVED_T:
        return []

    # state -> (depth, parent state, move that led from parent to state)
    fwd: dict = {start: (0, None, None)}
    bwd: dict = {_SOLVED_T: (0, None, None)}
    f_frontier, b_frontier = [start], [_SOLVED_T]
    f_depth = b_depth = 0

    while f_depth + b_depth < max_depth and f_frontier and b_frontier:
        if len(f_frontier) <= len(b_frontier):
            own, other, frontier, depth = fwd, bwd, f_frontier, f_depth
            forward = True
        else:
            own, other, frontier, depth = bwd, fwd, b_frontier, b_depth
            forward = False

        nxt = []
        for s in frontier:
            for m in MOVES:
                n = GETTERS[m](s)
                if n in own:
                    continue
                own[n] = (depth + 1, s, m)
                if n in other:
                    return _build_path(n, fwd, bwd)
                nxt.append(n)

        if forward:
            f_frontier, f_depth = nxt, f_depth + 1
        else:
            b_frontier, b_depth = nxt, b_depth + 1
    return None


def distance(state: str, max_depth: int = 8) -> int | None:
    """Exact shortest distance in moves, or ``None`` if greater than ``max_depth``."""
    path = shortest_path(state, max_depth)
    return None if path is None else len(path)


@lru_cache(maxsize=8192)
def shortest_path_cached(state: str, max_depth: int = 8) -> tuple[str, ...] | None:
    path = shortest_path(state, max_depth)
    return None if path is None else tuple(path)
