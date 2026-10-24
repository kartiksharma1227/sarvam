"""Deterministic checks the LLM output must pass, beyond the Pydantic schemas.

Each function returns a list of human-readable problems; the LLM layer sends them back to the model.
"""

import re

from app.pipeline.timing import drawables, normalize, resolve_cues
from app.schemas.plan import LessonPlan
from app.schemas.script import Script
from app.tts.base import Word

SENTENCES_PER_SCENE = (2, 4)
MAX_WORDS_PER_SCENE = 60
TOTAL_WORDS = (230, 380)  # ~90-150 s at ~150 words per minute
MAX_PHRASE_WORDS = 4
MIN_DISTINCT_LAYOUTS = 3


def word_count(text: str) -> int:
    return len(text.split())


def sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+(?:\s+|$)", text.strip()) if s.strip()])


def check_plan(plan: LessonPlan) -> list[str]:
    errors = []
    ids = [s.id for s in plan.scenes]
    expected = [f"s{i}" for i in range(1, len(ids) + 1)]
    if ids != expected:
        errors.append(f"scene ids must be {expected} in order, got {ids}")
    if plan.scenes[0].purpose != "hook":
        errors.append("the first scene's purpose must be 'hook'")
    if plan.scenes[-1].purpose != "recap":
        errors.append("the last scene's purpose must be 'recap'")
    layouts = {s.layout for s in plan.scenes}
    if len(layouts) < MIN_DISTINCT_LAYOUTS:
        errors.append(
            f"use at least {MIN_DISTINCT_LAYOUTS} different layouts for variety, got {sorted(layouts)}"
        )
    return errors


def check_script(script: Script, plan: LessonPlan) -> list[str]:
    errors = []
    ids = [s.id for s in script.scenes]
    planned = [s.id for s in plan.scenes]
    if ids != planned:
        errors.append(
            f"script must have exactly the scenes {planned} in order, got {ids}"
        )
    total = 0
    for scene in script.scenes:
        words = word_count(scene.narration)
        total += words
        sentences = sentence_count(scene.narration)
        lo, hi = SENTENCES_PER_SCENE
        if not lo <= sentences <= hi:
            errors.append(f"{scene.id}: has {sentences} sentences, needs {lo}-{hi}")
        if words > MAX_WORDS_PER_SCENE:
            errors.append(f"{scene.id}: has {words} words, max {MAX_WORDS_PER_SCENE}")
    lo, hi = TOTAL_WORDS
    if not lo <= total <= hi:
        errors.append(
            f"total narration is {total} words, needs {lo}-{hi} (about 90-150 seconds spoken)"
        )
    return errors


def _occurrences(tokens: list[str], phrase: list[str]) -> int:
    n = len(phrase)
    return sum(1 for i in range(len(tokens) - n + 1) if tokens[i : i + n] == phrase)


def _check_timing_matches(layout: str, slots: dict, narration: str) -> list[str]:
    """Run the real cue matcher on the narration text: every phrase must get its own exact spot.

    Catches conflicts the per-phrase checks miss, e.g. two phrases that start on the same word.
    """
    words = [
        Word(text=w, start=float(i), end=i + 0.5)
        for i, w in enumerate(narration.split())
    ]
    items = drawables(layout, slots)
    return [
        f'{cue.target}: appear_on "{cue.phrase}" collides with another element\'s phrase '
        "(they start on the same words); choose different words for one of them"
        for cue in resolve_cues(items, words, duration=float(len(words)))
        if cue.method != "exact"
    ]


# Layouts whose items are drawn one after another: their phrases must be spoken in that order,
# otherwise e.g. the last step of a flow would appear before the first.
ORDERED_PREFIXES = {
    "flow": "nodes.",
    "cycle": "nodes.",
    "checklist": "items.",
    "timeline": "events.",
    "scale": "bands.",
    "bar_chart": "bars.",
}


def _check_order(layout: str, slots: dict, tokens: list[str]) -> list[str]:
    prefix = ORDERED_PREFIXES.get(layout)
    if not prefix:
        return []
    cursor = 0
    previous = None
    for d in drawables(layout, slots):
        if not d.target.startswith(prefix):
            continue
        phrase = normalize(d.phrase)
        n = len(phrase)
        position = next(
            (
                i
                for i in range(cursor, len(tokens) - n + 1)
                if tokens[i : i + n] == phrase
            ),
            None,
        )
        if position is None:
            if _occurrences(
                tokens, phrase
            ):  # spoken, but only before the previous item
                message = (
                    f'{d.target}: appear_on "{d.phrase}" must be spoken after "{previous}"; '
                    f"items of a {layout} are drawn in order, so pick phrases in narration order"
                )
                return [message]
            continue  # missing phrases are reported separately
        cursor = position + n
        previous = d.phrase
    return []


def _parse_range(text: str) -> tuple[float, float] | None:
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)", text or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def check_scene(layout: str, slots: dict, narration: str) -> list[str]:
    errors = []
    tokens = normalize(narration)
    uses: dict[tuple[str, ...], int] = {}
    for d in drawables(layout, slots):
        phrase = normalize(d.phrase)
        if not phrase:
            errors.append(f"{d.target}: appear_on is empty")
            continue
        if len(phrase) > MAX_PHRASE_WORDS:
            errors.append(
                f'{d.target}: appear_on "{d.phrase}" is too long; use 1-3 words'
            )
        found = _occurrences(tokens, phrase)
        if found == 0:
            errors.append(
                f'{d.target}: appear_on "{d.phrase}" is not an exact word-for-word phrase from the narration'
            )
            continue
        key = tuple(phrase)
        uses[key] = uses.get(key, 0) + 1
        if uses[key] > found:
            errors.append(
                f'{d.target}: appear_on "{d.phrase}" is used {uses[key]} times but appears only {found} time(s) in the narration'
            )

    errors += _check_order(layout, slots, tokens)
    if not errors:
        errors += _check_timing_matches(layout, slots, narration)

    if layout == "scale" and slots.get("marker_value") is not None:
        value = float(slots["marker_value"])
        ranges = [_parse_range(b.get("range", "")) for b in slots.get("bands", [])]
        if not any(r and r[0] <= value <= r[1] for r in ranges):
            errors.append(f"marker_value {value:g} is not inside any band range")
    if layout == "bar_chart":
        errors += _check_bar_units(slots.get("bars", []))
    return errors


def bar_unit(display: str) -> str:
    """The unit part of a bar's display text: "95 mg" -> "mg", "20%" -> "%", "$1.2k" -> "$"."""
    text = re.sub(r"(?<=\d)[kKmMbB]\b", "", display)  # 1.2k / 3M / 2B are plain numbers
    return re.sub(r"[\d.,\s]", "", text).lower()


def _check_bar_units(bars: list[dict]) -> list[str]:
    units = {bar_unit(b.get("display", "")) for b in bars}
    if len(units) > 1:
        shown = ", ".join(repr(b.get("display")) for b in bars)
        message = (
            f"bars use different units ({shown}); a bar chart compares one kind of quantity "
            "on one scale, so every bar must be the same unit (e.g. all mg per cup)"
        )
        return [message]
    return []
