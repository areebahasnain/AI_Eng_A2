"""DeepSeek-R1 local I/O. Only completed final moves count, never model thinking."""
from __future__ import annotations
import json
import re
from .adapters import InvalidOutput
from .cube import FACES, MOVES
from .contract import face_grids

LEGAL = frozenset(MOVES)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)
_FENCE = re.compile(r"^```(?:json|text)?\s*(.*?)\s*```$", re.I | re.S)
_BARE_MOVE = re.compile(r"^(?:final\s*(?:answer|move)?\s*:\s*)?([URFDLB](?:2|')?)\s*[.!]?\s*$", re.I)


def compact_deepseek_prompt(state: dict) -> str:
    """Preserve the local models' cube facts while reducing duplicate prose.

    Do not include a reference solve or shortest-path oracle. The model makes
    the choice; the same 18 moves, cube state and heuristic observations apply.
    """
    cube = state.get('cube_facelets', '')
    grids = state.get('faces_3x3') or face_grids(cube)
    faces = '\n'.join(f'{f}: ' + ' / '.join(grids[f]) for f in FACES)
    scores = state.get('one_step_sticker_scores') or {}
    scoring = ', '.join(
        f"{m}={scores[m]['matching_stickers']}" if isinstance(scores[m], dict) and 'matching_stickers' in scores[m]
        else f'{m}={scores[m]}' for m in MOVES if m in scores
    ) if isinstance(scores, dict) else ''
    return (
        "Solve the current 3x3 Rubik's Cube, one move at a time. The goal is all 9 stickers "
        "on each face matching the centre. Face names: U=up R=right F=front D=down "
        "L=left B=back. Each three-row face grid is viewed head-on. "
        "A bare letter is a 90-degree CLOCKWISE turn viewed from that face; "
        "' means counterclockwise, 2 means 180 degrees. The cube itself does not rotate. "
        "Orientation: U top=B left=L; R top=U left=F; F top=U left=L; "
        "D top=F left=L; L top=U left=B; B top=U left=R.\n"
        "CURRENT SIX FACES (rows separated by /):\n" + faces +
        '\n54-character state URFDLB: ' + cube +
        '\nAll 18 legal moves: ' + ' '.join(MOVES) +
        '\nRecent moves: ' + (' '.join(state.get('recent_moves', [])) or 'none') +
        '\nMoves remaining: ' + str(state.get('moves_remaining', '')) +
        '\nMoves revisiting a past state (prefer to avoid): ' +
        (' '.join(state.get('avoid_revisit_moves', [])) or 'none') +
        ('\nCorrect-position stickers after each possible move (one-step heuristic, not exact solve distance): ' + scoring if scoring else '') +
        "\nChoose YOUR OWN legal move; don't undo moves blindly. "
        "Final answer must be exactly one legal move like R or U2 or F'. "
        "No explanations, no thinking text, no JSON needed."
    )


def parse_deepseek_move(text: str) -> str:
    """Never scrape an action from reasoning or an incomplete <think> block."""
    if not isinstance(text, str) or not text.strip():
        raise InvalidOutput('DeepSeek returned no final answer text')
    value = _THINK_BLOCK.sub('', text).strip()
    if re.search(r'<\s*/?think\b', value, re.I):
        raise InvalidOutput('DeepSeek thinking was not finished')
    fence = _FENCE.fullmatch(value)
    if fence:
        value = fence.group(1).strip()
    if value.startswith('{'):
        try:
            data = json.loads(value)
        except ValueError as exc:
            raise InvalidOutput('DeepSeek final output is invalid JSON') from exc
        if not isinstance(data, dict) or set(data) != {'move'}:
            raise InvalidOutput('DeepSeek final JSON needs only a move field')
        move = data['move']
        if not isinstance(move, str) or move not in LEGAL:
            raise InvalidOutput('DeepSeek final JSON has an illegal move')
        return move
    if value.startswith('"'):
        try:
            quoted = json.loads(value)
        except ValueError:
            quoted = None
        if isinstance(quoted, str) and quoted in LEGAL:
            return quoted
    match = _BARE_MOVE.fullmatch(value)
    if match and match.group(1) in LEGAL:
        return match.group(1)
    raise InvalidOutput('DeepSeek did not produce one unambiguous legal final move')
