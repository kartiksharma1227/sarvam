"""An icon in the library (collection `icons`). Files live under MEDIA_DIR/icons/."""

from datetime import datetime
from typing import Annotated, Literal

from beanie import Document, Indexed
from pydantic import Field

from app.models.job import now


class Icon(Document):
    name: Annotated[str, Indexed(unique=True)]  # slug, e.g. "water-droplet"
    subject: str  # what the image model was asked to draw
    description: str
    tags: list[str] = Field(default_factory=list)
    svg_path: str  # relative to MEDIA_DIR
    png_path: str
    embedding: list[float]
    style_version: int
    source: Literal["seed", "generated"]
    usage_count: int = 0
    created_at: datetime = Field(default_factory=now)

    class Settings:
        name = "icons"

    def search_text(self) -> str:
        return search_text(self.name, self.description, self.tags)


def search_text(name: str, description: str, tags: list[str]) -> str:
    """What gets embedded for an icon."""
    return f"{name.replace('-', ' ')}. {description}. {', '.join(tags)}"
