"""Loading the system prompts in agents/prompts/."""

import json
import re
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def fill(template: str, **values: str) -> str:
    """Replace {name} placeholders (plain replace, so other braces in the text are left alone)."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


@cache
def layout_rules(layout: str) -> str:
    """The catalogue section for one layout."""
    sections = re.split(r"^## ", load_prompt("layouts"), flags=re.MULTILINE)
    for section in sections:
        if section.startswith(layout + "\n"):
            return "## " + section.strip()
    raise KeyError(f"No rules for layout {layout!r} in layouts.md")


def as_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
