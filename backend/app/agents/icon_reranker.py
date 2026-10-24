from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, create_model

from app.agents.llm import LLM
from app.agents.prompting import load_prompt
from app.schemas.common import Strict

NONE = "none"
Slug = Annotated[
    str, Field(min_length=2, max_length=40, pattern=r"^[a-z0-9]+(-[a-z0-9]+){0,3}$")
]


class NewIcon(Strict):
    name: Slug
    subject: str = Field(min_length=3, max_length=140)
    description: str = Field(min_length=3, max_length=200)
    tags: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        min_length=3, max_length=6
    )


@dataclass
class Candidate:
    name: str
    description: str
    score: float


@dataclass
class IconContext:
    """Where an icon is used: helps both search and the reranker."""

    scene_title: str
    label: str  # the text drawn next to the icon, e.g. a node label
    narration: str


def _output_model(names: list[str]):
    choices = tuple(dict.fromkeys([*names, NONE]))
    return create_model(
        "IconChoice",
        __base__=Strict,
        choice=(Literal[choices], ...),
        new_icon=(NewIcon | None, None),
    )


async def rerank_icon(
    llm: LLM, query: str, context: IconContext, candidates: list[Candidate]
) -> tuple[str, NewIcon | None]:
    """Returns (chosen candidate name, None) or ("none", the icon to draw)."""
    listing = (
        "\n".join(
            f"- {c.name}: {c.description} (similarity {c.score:.2f})"
            for c in candidates
        )
        or "(the library has no candidates)"
    )
    user = (
        f"Icon query: {query}\n"
        f"Scene: {context.scene_title}\n"
        f"Label next to the icon: {context.label or '(none)'}\n"
        f"Narration: {context.narration}\n\n"
        f"Candidates:\n{listing}"
    )

    def check(result) -> list[str]:
        if result.choice == NONE and result.new_icon is None:
            return ['choice is "none", so new_icon must describe the icon to draw']
        return []

    result = await llm.structured(
        agent=f"icon_reranker[{query}]",
        tier="fast",
        system=load_prompt("icon_reranker"),
        user=user,
        output_model=_output_model([c.name for c in candidates]),
        check=check,
    )
    if result.choice == NONE:
        return NONE, result.new_icon
    return result.choice, None
