"""Designer output: a scene's layout slots. Field names match renderer/src/layouts/*.jsx exactly.

Length limits come from the renderer's geometry boxes, so text that validates always fits on screen.
"""

from functools import lru_cache
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, create_model, model_validator

from app.schemas.common import Layout, Strict

# An exact 1-3 word phrase from the narration; the element draws on when it is spoken.
Phrase = Annotated[str, Field(min_length=1, max_length=40)]
IconQuery = Annotated[str, Field(min_length=1, max_length=40)]
Color = Literal["red", "orange", "yellow", "green", "blue"]


class TitleCardSlots(Strict):
    heading: str = Field(min_length=1, max_length=40)
    subheading: str | None = Field(default=None, max_length=60)
    icon_query: IconQuery | None = None
    subheading_appear_on: Phrase | None = None


class Node(Strict):
    label: str = Field(min_length=1, max_length=14)
    icon_query: IconQuery
    appear_on: Phrase


class FlowSlots(Strict):
    nodes: list[Node] = Field(min_length=2, max_length=4)
    arrow_labels: list[Annotated[str, Field(max_length=12)]] | None = None

    @model_validator(mode="after")
    def _arrow_labels_match_arrows(self):
        if (
            self.arrow_labels is not None
            and len(self.arrow_labels) != len(self.nodes) - 1
        ):
            raise ValueError(
                f"arrow_labels needs exactly {len(self.nodes) - 1} entries (one per arrow), or null"
            )
        return self


class CycleSlots(Strict):
    nodes: list[Node] = Field(min_length=3, max_length=5)


class ColumnHeader(Strict):
    header: str = Field(min_length=1, max_length=16)
    icon_query: IconQuery
    appear_on: Phrase


class Cell(Strict):
    icon_query: IconQuery | None = None
    value: str = Field(min_length=1, max_length=10)
    caption: str = Field(min_length=1, max_length=16)
    appear_on: Phrase | None = None


class Row(Strict):
    left: Cell
    right: Cell
    appear_on: Phrase | None = None

    @model_validator(mode="after")
    def _has_trigger(self):
        if not self.appear_on and not (self.left.appear_on and self.right.appear_on):
            raise ValueError(
                "each row needs appear_on on both cells (preferred) or on the row"
            )
        return self


class ComparisonSlots(Strict):
    left: ColumnHeader
    right: ColumnHeader
    rows: list[Row] = Field(min_length=1, max_length=3)


class StatSlots(Strict):
    value: str = Field(min_length=1, max_length=8)
    caption: str = Field(min_length=1, max_length=40)
    icon_query: IconQuery
    appear_on: Phrase


class ScaleStat(Strict):
    value: str = Field(min_length=1, max_length=12)
    caption: str = Field(min_length=1, max_length=30)
    icon_query: IconQuery | None = None
    appear_on: Phrase | None = None


class Band(Strict):
    label: str = Field(min_length=1, max_length=12)
    range: str = Field(min_length=1, max_length=12)
    color: Color
    appear_on: Phrase


class ScaleSlots(Strict):
    stat: ScaleStat | None = None
    bands: list[Band] = Field(min_length=2, max_length=5)
    marker_value: float | None = None
    marker_appear_on: Phrase | None = None


class ChecklistItem(Strict):
    text: str = Field(min_length=1, max_length=24)
    icon_query: IconQuery
    appear_on: Phrase


class ChecklistSlots(Strict):
    items: list[ChecklistItem] = Field(min_length=2, max_length=5)


class TimelineEvent(Strict):
    date_label: str = Field(min_length=1, max_length=10)
    text: str = Field(min_length=1, max_length=28)
    icon_query: IconQuery
    appear_on: Phrase


class TimelineSlots(Strict):
    events: list[TimelineEvent] = Field(min_length=3, max_length=5)


class VennSide(Strict):
    label: str = Field(min_length=1, max_length=16)
    icon_query: IconQuery
    appear_on: Phrase


class VennBoth(Strict):
    label: str = Field(min_length=1, max_length=20)
    appear_on: Phrase


class VennSlots(Strict):
    left: VennSide
    right: VennSide
    both: VennBoth


class Bar(Strict):
    label: str = Field(min_length=1, max_length=12)
    # The quantity the bar's length is computed from (data, not a coordinate).
    value: float = Field(ge=0)
    display: str = Field(
        min_length=1, max_length=8
    )  # how the value is written, e.g. "35%"
    appear_on: Phrase


class BarChartSlots(Strict):
    bars: list[Bar] = Field(min_length=2, max_length=6)
    caption: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _some_bar_has_a_value(self):
        if max(bar.value for bar in self.bars) <= 0:
            raise ValueError("at least one bar needs a value above 0")
        return self


class BeforeAfterPanel(Strict):
    header: str = Field(min_length=1, max_length=16)
    icon_query: IconQuery
    caption: str = Field(min_length=1, max_length=40)
    appear_on: Phrase


class BeforeAfterSlots(Strict):
    before: BeforeAfterPanel
    after: BeforeAfterPanel
    arrow_label: str | None = Field(default=None, max_length=12)


SLOTS_BY_LAYOUT: dict[str, type[Strict]] = {
    "title_card": TitleCardSlots,
    "flow": FlowSlots,
    "comparison": ComparisonSlots,
    "stat": StatSlots,
    "scale": ScaleSlots,
    "checklist": ChecklistSlots,
    "cycle": CycleSlots,
    "timeline": TimelineSlots,
    "venn": VennSlots,
    "bar_chart": BarChartSlots,
    "before_after": BeforeAfterSlots,
}


class _SceneBase(Strict):
    id: str
    title: str = Field(min_length=1, max_length=40)
    narration: str = Field(min_length=1)


def _scene_model(layout: str) -> type[_SceneBase]:
    name = "".join(part.title() for part in layout.split("_")) + "Scene"
    return create_model(
        name,
        __base__=_SceneBase,
        layout=(Literal[layout], ...),
        slots=(SLOTS_BY_LAYOUT[layout], ...),
    )


_SCENE_MODELS = tuple(_scene_model(layout) for layout in SLOTS_BY_LAYOUT)
SceneSpec = Annotated[Union[_SCENE_MODELS], Field(discriminator="layout")]  # noqa: UP007 (built from a tuple)
scene_spec_adapter: TypeAdapter = TypeAdapter(SceneSpec)


def validate_scene_spec(data: dict) -> BaseModel:
    """Validate a full scene (id, title, narration, layout, slots) against its layout's rules."""
    return scene_spec_adapter.validate_python(data)


@lru_cache
def designer_output_model(layout: Layout) -> type[Strict]:
    """What the designer returns for one layout: a scene title plus that layout's slots."""
    name = "".join(part.title() for part in layout.split("_")) + "Design"
    return create_model(
        name,
        __base__=Strict,
        title=(
            str,
            Field(
                min_length=1,
                max_length=40,
                description="Short scene title shown at the top",
            ),
        ),
        slots=(SLOTS_BY_LAYOUT[layout], ...),
    )
