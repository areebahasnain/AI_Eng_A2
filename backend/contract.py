"""The single game-action contract shared by every model.

Both API styles (Decisions API for Jev / Luna / Clef, chat completions for
Opus) are built from the *same* state object, the *same* move definitions and
the *same* instruction wording defined here.  Only the transport differs.
"""
from __future__ import annotations

import json

from .cube import FACES, MOVES, SOLVED

QUESTION_ID = "next_move"

FACE_NAMES = {
    "U": "upper",
    "D": "down",
    "R": "right",
    "L": "left",
    "F": "front",
    "B": "back",
}


def _describe(move: str) -> str:
    face = FACE_NAMES[move[0]]
    if move.endswith("2"):
        return f"Turn the {face} face by 180 degrees"
    if move.endswith("'"):
        return f"Turn the {face} face counterclockwise by 90 degrees"
    return f"Turn the {face} face clockwise by 90 degrees"


# move -> human description (the "criteria" of the Decisions choice question).
MOVE_CRITERIA: dict[str, str] = {m: _describe(m) for m in MOVES}

LAYOUT_LEGEND = (
    "The cube is a standard 3x3 given as a 54-character facelet string in the order "
    "U, R, F, D, L, B faces (9 facelets each, read row by row as seen looking directly at that face). "
    "Each letter names the face whose colour is on that sticker. The solved cube is "
    f"{' '.join(f * 9 for f in FACES)} (spaces added for readability only). "
    "Face grid orientation: U top row touches B and left column touches L; "
    "R top row touches U and left column touches F; "
    "F top row touches U and left column touches L; "
    "D top row touches F and left column touches L; "
    "L top row touches U and left column touches B; "
    "B top row touches U and left column touches R. "
    "A move turns the named face 90 degrees clockwise as seen looking at that face; "
    "' means counterclockwise and 2 means a half turn."
)

# Identical wording for every model (the assignment requires this).
QUESTION_INSTRUCTIONS = (
    "Choose the single next move most likely to progress toward the solved cube. "
    + LAYOUT_LEGEND
)

CHAT_SYSTEM_PROMPT = (
    "You are playing a Rubik's Cube solving game. Each turn you receive the current cube state "
    "and must answer with exactly ONE move from the allowed list, as a JSON object "
    '{"move": "<move>"} and nothing else (no explanation, no markdown). '
    + LAYOUT_LEGEND
)


def face_grids(cube_state: str) -> dict[str, list[str]]:
    """Six *face-on* 3x3 sticker grids in the engine's U R F D L B order.

    These are observations, never an oracle or a suggested move.  A row contains
    three space-separated face-colour letters, top to bottom as viewed head-on.
    """
    if len(cube_state) != 54:
        raise ValueError("Expected exactly 54 facelet letters")
    return {
        face: [" ".join(cube_state[i * 9 + r * 3 : i * 9 + r * 3 + 3]) for r in range(3)]
        for i, face in enumerate(FACES)
    }


def build_game_state(
    cube_state: str, recent_moves: list[str], moves_remaining: int, *,
    readable_grids: bool = False,
) -> dict:
    """Identical state for competitors within each provider.

    ``readable_grids`` is Ollama-only; hosted OpenRouter payloads remain unchanged
    so existing restricted-key cache entries and the teacher's budget remain safe.
    """
    state = {
        "cube_facelets": cube_state,
        "solved_facelets": SOLVED,
        "recent_moves": list(recent_moves),
        "moves_remaining": moves_remaining,
    }
    if readable_grids:
        state["faces_3x3"] = face_grids(cube_state)
    return state


def decisions_questions() -> dict:
    return {
        QUESTION_ID: {
            "type": "choice",
            "instructions": QUESTION_INSTRUCTIONS,
            "criteria": dict(MOVE_CRITERIA),
        }
    }


def chat_user_message(game_state: dict) -> str:
    return (
        "Choose the single next move most likely to progress toward the solved cube.\n"
        "Current state (JSON):\n"
        + json.dumps(game_state)
        + "\nAllowed moves with meanings (JSON):\n"
        + json.dumps(MOVE_CRITERIA)
        + '\nReply with exactly one JSON object: {"move": "<one of the allowed moves>"}'
    )


CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"move": {"type": "string", "enum": list(MOVES)}},
    "required": ["move"],
    "additionalProperties": False,
}


# Local Ollama observation and answer contract.
# Neutrality is intentional.  An old response example used the literal move U,
# which was a plausible source of the strong U-repetition seen in saved logs.
# The 18 moves remain identical; only the presentation order may vary.
OLLAMA_COMMON_GUIDE = (
    "Solve the fixed-orientation 3x3 cube, making all stickers on each face match "
    "that face's centre. The observation contains 54 stickers in URFDLB order "
    "and six matching labeled 3x3 grids. Each grid is viewed face-on from "
    "outside that face, rows top-to-bottom and columns left-to-right. "
    "Face orientation: on U the top edge meets B and left edge L; "
    "on R top meets U and left meets F; on F top meets U and left meets L; "
    "on D top meets F and left meets L; on L top meets U and left meets B; "
    "on B top meets U and left meets R. "
    "Use exactly one of the 18 legal face turns in the provided action set. "
    "A bare face letter means 90 degrees clockwise looking directly at that "
    "face being turned from outside; a trailing apostrophe means 90 degrees counterclockwise; "
    "a trailing 2 means 180 degrees. A half turn counts as one move. "
    "The cube never rotates globally. The initial cube has a proven 3-turn "
    "shortest solution, but a wrong move may increase that distance. "
    "Consider how successive moves affect the whole cube before selecting this "
    "turn. Avoid repeating a cycle or immediately making the inverse of the "
    "previous move when that returns to an already seen state. "
    "The avoid_revisit_moves field lists actions leading to previously observed "
    "states; it is advice rather than an illegal-move list. "
    "If one_step_sticker_scores is present, treat it only as an imperfect "
    "heuristic, never as the true shortest distance. "
    "Never invent stickers, mutate the input state, or return more than one move."
)

OLLAMA_CHAT_SYSTEM_PROMPT = (
    OLLAMA_COMMON_GUIDE + " Return exactly one JSON object with a single key "
    "named move whose value is one legal action string. No example moves, "
    "explanations, markdown, extra keys, or other text."
)

# For a controlled prompt ablation only.  Do not mix legacy and neutral
# trials when reporting solve rates.  Legacy includes the old U exemplar.
OLLAMA_LEGACY_CHAT_SYSTEM_PROMPT = (
    OLLAMA_COMMON_GUIDE + ' Reply with ONLY a JSON object {"move": "U"} '
    "with U replaced by exactly one allowed move; no explanation or markdown."
)


def ollama_decisions_questions(move_order=None) -> dict:
    """Same legal choices and task instructions used by all local competitors."""
    order = list(move_order) if move_order is not None else list(MOVES)
    if set(order) != set(MOVES) or len(order) != len(MOVES):
        raise ValueError("move_order must contain the 18 legal moves exactly once")
    return {QUESTION_ID: {
        "type": "choice",
        "instructions": OLLAMA_COMMON_GUIDE,
        "criteria": {m: MOVE_CRITERIA[m] for m in order},
    }}


def ollama_chat_user_message(game_state: dict, move_order=None) -> str:
    """Neutral observation and the same 18 move meanings as System One."""
    order = list(move_order) if move_order is not None else list(MOVES)
    if set(order) != set(MOVES) or len(order) != len(MOVES):
        raise ValueError("move_order must contain the 18 legal moves exactly once")
    return (
        "Current cube observation (JSON):\n" + json.dumps(game_state, separators=(",", ":"))
        + "\nThe 18 allowed moves and their meanings (JSON):\n"
        + json.dumps({m: MOVE_CRITERIA[m] for m in order}, separators=(",", ":"))
        + "\nReturn exactly one legal move as the value of the move field in a JSON object."
    )


def ollama_chat_response_schema(move_order=None) -> dict:
    """All legal moves, with a non-fixed enum order to reduce position bias."""
    order = list(move_order) if move_order is not None else list(MOVES)
    if set(order) != set(MOVES) or len(order) != len(MOVES):
        raise ValueError("move_order must contain the 18 legal moves exactly once")
    return {"type": "object", "properties": {
        "move": {"type": "string", "enum": order}
    }, "required": ["move"], "additionalProperties": False}
