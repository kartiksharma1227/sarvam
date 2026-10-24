"""Planner output: the lesson outline."""

from typing import Literal

from pydantic import Field

from app.schemas.common import Layout, Strict

Purpose = Literal["hook", "analogy", "mechanism", "numbers", "recap"]


class PlannedScene(Strict):
    id: str = Field(description="s1, s2, ... in order")
    purpose: Purpose
    key_point: str = Field(
        max_length=200, description="The one idea this scene teaches"
    )
    layout: Layout = Field(description="Which layout template draws this scene")
    key_numbers: list[str] = Field(
        description="Real figures to show on screen; empty if none"
    )


class LessonPlan(Strict):
    title: str = Field(max_length=60)
    audience: str = Field(max_length=120)
    learning_objectives: list[str] = Field(min_length=2, max_length=4)
    hook: str = Field(max_length=200)
    analogy: str = Field(max_length=200)
    scenes: list[PlannedScene] = Field(min_length=5, max_length=8)
