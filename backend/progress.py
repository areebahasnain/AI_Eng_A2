"""Ollama-only post-decision progress diagnostics; never sent to any model.

The cube is exactly 3 face turns away at the start. Measuring arbitrary 3x3
positions' exact optimal distance can be prohibitively expensive, so we compute
exact shortest-path distances only through a safe breadth-first-search horizon.
A missing distance means *strictly more* than that horizon, not zero.
"""
from __future__ import annotations

from functools import lru_cache

from .cube import SOLVED
from .solver import distance

EXACT_DISTANCE_HORIZON = 7


@lru_cache(maxsize=4096)
def exact_local_distance(state: str) -> int | None:
    """Return guaranteed exact HTM distance through 7 turns, else unknown (>7)."""
    return distance(state, EXACT_DISTANCE_HORIZON)


def measure_progress(before: int | None, after: int | None) -> dict:
    """Compare distance with the solved cube; don't guess when both are unknown."""
    if before is not None and after is not None:
        delta = after - before
        change = "closer" if delta < 0 else "farther" if delta > 0 else "same"
    elif before == EXACT_DISTANCE_HORIZON and after is None:
        # Any successor outside the horizon is farther than a 7-move position.
        delta, change = None, "farther"
    elif before is None and after == EXACT_DISTANCE_HORIZON:
        delta, change = None, "closer"
    else:
        delta, change = None, "unknown"
    return {
        "distance_before": before,
        "distance_after": after,
        "distance_delta": delta,  # after - before; negative means progress
        "distance_change": change,
        "distance_horizon": EXACT_DISTANCE_HORIZON,
        "distance_after_label": str(after) if after is not None else f">{EXACT_DISTANCE_HORIZON}",
        "distance_exact": after is not None,
    }


# Non-oracle state-memory feedback for the *local* experiment.  A revisit can
# be detected by comparing 54 sticker letters; it does not require a solver.
from .cube import MOVES, apply_move


def local_cycle_observation(current: str, visited_states: set[str]) -> dict:
    """List legal moves returning to already visited states, not good moves.

    Returned to *all four* Ollama models under the same policy.  This supplies
    memory of the model's own trajectory, NOT solved-distance or a solution.
    """
    return {
        "avoid_revisit_moves": [
            move for move in MOVES if apply_move(current, move) in visited_states
        ],
    }


def repeated_closed_loop(states: list[str], moves: list[str], max_length: int = 4) -> int | None:
    """Return a short repeated closed-cycle length, if observed twice in a row.

    Only state equality and recorded actions are used.  For D,D',D,D' this
    returns 2. It never manufactures or replaces a model-selected action.
    """
    for width in range(2, min(max_length, len(moves) // 2) + 1):
        if (moves[-2*width:-width] == moves[-width:]
                and states[-1] == states[-1-width] == states[-1-2*width]):
            return width
    return None


def one_step_sticker_observation(current: str, visited_states: set[str]) -> dict:
    """Explain consequences of ALL 18 legal actions without using a solver.

    Matching-sticker count is a transparent one-step heuristic, NOT the
    shortest-path distance. It may rise even as true cube distance increases.
    Exactly the same observation policy is applied to all four Ollama models.
    """
    from .cube import correct_facelets
    scores = {}
    for move in MOVES:
        next_state = apply_move(current, move)
        # Compact: avoid_revisit_moves already encodes revisits. The old
        # nested 18-item scorecard repeated it and was distracting/expensive
        # for the local 9B decision model.
        scores[move] = correct_facelets(next_state)
    return {
        'current_matching_stickers': correct_facelets(current),
        'one_step_sticker_scores': scores,
    }
