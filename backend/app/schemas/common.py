from typing import Literal

from pydantic import BaseModel, ConfigDict

LAYOUTS = (
    "title_card",
    "flow",
    "comparison",
    "stat",
    "scale",
    "checklist",
    "cycle",
    "timeline",
    "venn",
    "bar_chart",
    "before_after",
)
Layout = Literal[
    "title_card",
    "flow",
    "comparison",
    "stat",
    "scale",
    "checklist",
    "cycle",
    "timeline",
    "venn",
    "bar_chart",
    "before_after",
]


class Strict(BaseModel):
    """Rejects unknown fields, so a typo from the LLM fails validation instead of being dropped."""

    model_config = ConfigDict(extra="forbid")
