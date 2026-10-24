"""Scriptwriter / editor output: narration per scene."""

from pydantic import Field

from app.schemas.common import Strict


class SceneNarration(Strict):
    id: str
    narration: str = Field(min_length=1)


class Script(Strict):
    scenes: list[SceneNarration] = Field(min_length=1)
