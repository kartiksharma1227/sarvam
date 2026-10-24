"""Turn each drawable's `appear_on` phrase into the moment that phrase is spoken.

Cue target names must match the ones the renderer's layouts read (see renderer/src/layouts/*.jsx).
"""

import difflib
import logging
import re
from dataclasses import dataclass

from app.tts.base import Word

log = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.8
LEAD_IN = 0.3  # earliest time for an unresolved first element
TAIL = 0.5  # keep unresolved elements this far before the audio ends


@dataclass
class Drawable:
    target: str
    phrase: str


@dataclass
class CueResult:
    target: str
    phrase: str
    start: float
    method: str  # exact | fuzzy | interpolated
    matched: str = ""


def normalize(text: str) -> list[str]:
    """Lowercase tokens; hyphens and slashes split words ("on-time" -> ["on", "time"])."""
    text = re.sub(r"[-–—/]", " ", text.lower())
    text = re.sub(r"[^\w%\s]", "", text)
    return text.split()


def drawables(layout: str, slots: dict) -> list[Drawable]:
    """Every element of a scene that has a trigger phrase, in the order the layout draws them."""
    found: list[Drawable] = []

    def add(target: str, item: dict | None, key: str = "appear_on") -> None:
        if item and item.get(key):
            found.append(Drawable(target, item[key]))

    if layout in ("flow", "cycle"):
        for i, node in enumerate(slots.get("nodes", [])):
            add(f"nodes.{i}", node)
    elif layout == "comparison":
        add("left", slots.get("left"))
        add("right", slots.get("right"))
        for r, row in enumerate(slots.get("rows", [])):
            if row.get("left", {}).get("appear_on") or row.get("right", {}).get(
                "appear_on"
            ):
                add(f"rows.{r}.left", row.get("left"))
                add(f"rows.{r}.right", row.get("right"))
            else:
                add(f"rows.{r}", row)
    elif layout == "stat":
        add("stat", slots)
    elif layout == "scale":
        add("stat", slots.get("stat"))
        for i, band in enumerate(slots.get("bands", [])):
            add(f"bands.{i}", band)
        add("marker", slots, key="marker_appear_on")
    elif layout == "checklist":
        for i, item in enumerate(slots.get("items", [])):
            add(f"items.{i}", item)
    elif layout == "timeline":
        for i, event in enumerate(slots.get("events", [])):
            add(f"events.{i}", event)
    elif layout == "title_card":
        add("subheading", slots, key="subheading_appear_on")
    elif layout == "venn":
        add("left", slots.get("left"))
        add("right", slots.get("right"))
        add("both", slots.get("both"))
    elif layout == "bar_chart":
        for i, bar in enumerate(slots.get("bars", [])):
            add(f"bars.{i}", bar)
    elif layout == "before_after":
        add("before", slots.get("before"))
        add("after", slots.get("after"))
    return found


def _tokens(words: list[Word]) -> list[tuple[str, float]]:
    """Flatten TTS words into normalized tokens; a split word keeps its original start time."""
    return [(part, w.start) for w in words for part in normalize(w.text)]


def _find_exact(
    tokens: list[str], phrase: list[str], start: int, used: set[int]
) -> int | None:
    n = len(phrase)
    for i in range(start, len(tokens) - n + 1):
        if i not in used and tokens[i : i + n] == phrase:
            return i
    return None


def _find_fuzzy(
    tokens: list[str], phrase: list[str], used: set[int]
) -> tuple[int, float] | None:
    target = " ".join(phrase)
    best: tuple[int, float] | None = None
    for size in sorted({max(1, len(phrase) - 1), len(phrase), len(phrase) + 1}):
        for i in range(len(tokens) - size + 1):
            if i in used:
                continue
            ratio = difflib.SequenceMatcher(
                None, target, " ".join(tokens[i : i + size])
            ).ratio()
            if best is None or ratio > best[1]:
                best = (i, ratio)
    return best if best and best[1] >= FUZZY_THRESHOLD else None


def resolve_cues(
    items: list[Drawable], words: list[Word], duration: float
) -> list[CueResult]:
    """Match phrases in narration order (falling back to anywhere unused), then fill gaps evenly."""
    flat = _tokens(words)
    tokens = [t for t, _ in flat]
    used: set[int] = set()
    cursor = 0
    results: list[CueResult | None] = []

    for item in items:
        phrase = normalize(item.phrase)
        if not phrase:
            results.append(None)
            continue
        idx = _find_exact(tokens, phrase, cursor, used)
        if idx is None:
            idx = _find_exact(tokens, phrase, 0, used)
        if idx is not None:
            used.add(idx)
            cursor = idx + len(phrase)
            matched = " ".join(tokens[idx : idx + len(phrase)])
            results.append(
                CueResult(item.target, item.phrase, flat[idx][1], "exact", matched)
            )
            continue
        fuzzy = _find_fuzzy(tokens, phrase, used)
        if fuzzy is not None:
            idx, ratio = fuzzy
            used.add(idx)
            cursor = idx + len(phrase)
            matched = " ".join(tokens[idx : idx + len(phrase)])
            log.info(
                "Fuzzy cue %s: %r ~ %r (%.2f)", item.target, item.phrase, matched, ratio
            )
            results.append(
                CueResult(item.target, item.phrase, flat[idx][1], "fuzzy", matched)
            )
            continue
        log.warning(
            "Cue %s: phrase %r not found in narration; spacing it evenly",
            item.target,
            item.phrase,
        )
        results.append(None)

    return _interpolate(items, results, duration)


def _interpolate(
    items: list[Drawable], results: list[CueResult | None], duration: float
) -> list[CueResult]:
    """Place unresolved cues evenly between their resolved neighbours."""
    out: list[CueResult] = []
    i = 0
    while i < len(results):
        if results[i] is not None:
            out.append(results[i])
            i += 1
            continue
        j = i
        while j < len(results) and results[j] is None:
            j += 1
        lo = results[i - 1].start if i > 0 else LEAD_IN
        hi = results[j].start if j < len(results) else max(lo, duration - TAIL)
        gap = j - i
        if i == 0 and j == len(results):
            # Nothing resolved at all: spread across the whole narration, first one at the lead-in.
            starts = [lo + (hi - lo) * k / gap for k in range(gap)]
        else:
            starts = [lo + (hi - lo) * (k + 1) / (gap + 1) for k in range(gap)]
        for k, start in enumerate(starts):
            out.append(
                CueResult(
                    items[i + k].target,
                    items[i + k].phrase,
                    round(start, 3),
                    "interpolated",
                )
            )
        i = j
    return out


def cues_for_scene(
    layout: str, slots: dict, words: list[Word], duration: float
) -> list[CueResult]:
    return resolve_cues(drawables(layout, slots), words, duration)
