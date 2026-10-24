"""The icon library: find the right icon for an icon_query, or draw a new one and keep it.

pick(): job cache -> exact name -> vector search top-k -> rerank (fast model) -> reuse, or
generate on a miss (capped per video; beyond the cap the closest candidate is used).
"""

import asyncio
import logging
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from beanie.odm.operators.update.general import Inc
from pymongo.errors import DuplicateKeyError

from app.agents.icon_reranker import NONE, Candidate, IconContext, NewIcon, rerank_icon
from app.agents.llm import LLM
from app.config import settings
from app.icons.embed import Embedder
from app.icons.generate import Generator, png_to_svg
from app.icons.style import STYLE_VERSION
from app.models.icon import Icon, search_text
from app.models.job import IconChoice, Job

log = logging.getLogger(__name__)

ICONS_DIR = "icons"  # under MEDIA_DIR
LABEL_KEYS = ("label", "text", "header", "heading", "caption", "value")
VECTOR_INDEX = "icon_embedding"


def normalise_query(query: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", query.lower()))


def slugify(text: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def icon_path(name: str) -> str:
    """Path of an icon's SVG relative to MEDIA_DIR."""
    return f"{ICONS_DIR}/{name}.svg"


def icon_queries(slots) -> list[tuple[str, str]]:
    """Every (icon_query, label drawn next to it) in a scene's slots, first use of each query only."""
    found: dict[str, str] = {}

    def walk(value) -> None:
        if isinstance(value, dict):
            query = value.get("icon_query")
            if isinstance(query, str) and query and query not in found:
                found[query] = next(
                    (str(value[k]) for k in LABEL_KEYS if value.get(k)), ""
                )
            for key, item in value.items():
                if key != "icon_query":
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(slots)
    return list(found.items())


class IconLibrary:
    def __init__(
        self,
        llm: LLM,
        embedder: Embedder,
        generator: Generator,
        media_root: Path,
        *,
        max_new_per_video: int | None = None,
        k: int | None = None,
        search_mode: str | None = None,
    ):
        self.llm = llm
        self.embedder = embedder
        self.generator = generator
        self.media_root = media_root
        self.max_new = (
            settings.icon_max_new_per_video
            if max_new_per_video is None
            else max_new_per_video
        )
        self.k = k or settings.icon_search_k
        self.search_mode = search_mode or settings.icon_search
        self._names: list[str] = []
        self._descriptions: dict[str, str] = {}
        self._matrix = np.zeros((0, embedder.dimensions), dtype=np.float32)
        self._loaded = False
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ---- library contents ----

    async def load(self) -> None:
        icons = await Icon.find_all().sort("+name").to_list()
        self._names = [i.name for i in icons]
        self._descriptions = {i.name: i.description for i in icons}
        self._matrix = np.array([i.embedding for i in icons], dtype=np.float32).reshape(
            len(icons), self.embedder.dimensions
        )
        self._loaded = True

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await self.load()

    async def names(self) -> list[str]:
        await self._ensure_loaded()
        return list(self._names)

    def _add(self, icon: Icon) -> None:
        self._names.append(icon.name)
        self._descriptions[icon.name] = icon.description
        row = np.array([icon.embedding], dtype=np.float32)
        self._matrix = np.vstack([self._matrix, row])

    async def search(self, text: str, k: int | None = None) -> list[Candidate]:
        await self._ensure_loaded()
        k = k or self.k
        if not self._names:
            return []
        vector = (await self.embedder.embed([text], self.llm.usage))[0]
        if self.search_mode == "atlas":
            return await self._atlas_search(vector, k)
        scores = self._matrix @ vector
        top = np.argsort(-scores, kind="stable")[:k]
        return [
            Candidate(
                self._names[i], self._descriptions[self._names[i]], float(scores[i])
            )
            for i in top
        ]

    async def _atlas_search(self, vector: np.ndarray, k: int) -> list[Candidate]:
        """Atlas Vector Search (index created by `python -m app.icons.seed --atlas-index`)."""
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": vector.tolist(),
                    "numCandidates": k * 10,
                    "limit": k,
                }
            },
            {
                "$project": {
                    "name": 1,
                    "description": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        rows = await Icon.aggregate(pipeline).to_list()
        # Atlas reports cosine as (1 + cos) / 2; convert back so scores match the NumPy path.
        return [
            Candidate(r["name"], r["description"], r["score"] * 2 - 1) for r in rows
        ]

    async def create(
        self,
        name: str,
        subject: str,
        description: str,
        tags: list[str],
        source: str = "generated",
    ) -> Icon:
        """Draw a new icon, save its files, embed it and add it to the library."""
        await self._ensure_loaded()
        png = await self.generator.generate(subject, self.llm.usage)
        cleaned, svg = await asyncio.to_thread(png_to_svg, png)  # CPU-heavy
        text = search_text(name, description, tags)
        embedding = (await self.embedder.embed([text], self.llm.usage))[0]
        # Files are written only once every API call has succeeded.
        folder = self.media_root / ICONS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.png").write_bytes(cleaned)
        (folder / f"{name}.svg").write_text(svg)
        icon = Icon(
            name=name,
            subject=subject,
            description=description,
            tags=tags,
            svg_path=icon_path(name),
            png_path=f"{ICONS_DIR}/{name}.png",
            embedding=embedding.tolist(),
            style_version=STYLE_VERSION,
            source=source,
        )
        existing = await Icon.find_one(Icon.name == name)
        if existing is not None:  # redrawn (seed --redo): replace in place
            icon.id, icon.usage_count = existing.id, existing.usage_count
            await icon.replace()
            await self.load()
            return icon
        try:
            await icon.insert()
        except DuplicateKeyError:  # drawn concurrently by another process
            return await Icon.find_one(Icon.name == name)
        self._add(icon)
        return icon

    # ---- picking ----

    def _exact(self, query: str) -> str | None:
        slug = slugify(query)
        for name in (slug, slug.rstrip("s")):
            if name in self._descriptions:
                return name
        return None

    async def pick(self, query: str, context: IconContext, job: Job) -> IconChoice:
        await self._ensure_loaded()
        key = normalise_query(query)
        async with self._locks[key]:
            if key in job.icon_choices:
                return job.icon_choices[key]
            choice = await self._choose(query, context, job)
            job.icon_choices[key] = choice
            await Icon.find(Icon.name == choice.name).update(Inc({Icon.usage_count: 1}))
            return choice

    async def _choose(self, query: str, context: IconContext, job: Job) -> IconChoice:
        if name := self._exact(query):
            return IconChoice(name=name, how="exact")

        search_for = (
            f"{query} ({context.label})"
            if context.label and context.label.lower() != query.lower()
            else query
        )
        candidates = await self.search(search_for)
        choice, new = await rerank_icon(self.llm, query, context, candidates)
        if choice != NONE:
            return IconChoice(name=choice, how="reranked")

        # Two queries can ask for the same new icon ("down arrow", "downward arrow"): draw it once.
        async with self._locks[f"name:{new.name}"]:
            if existing := self._exact(
                new.name
            ):  # exists, just ranked outside the top k
                return IconChoice(name=existing, how="reranked")
            if len(job.icons_generated) >= self.max_new and candidates:
                log.warning(
                    "Icon cap (%d per video) reached; using %r for %r",
                    self.max_new,
                    candidates[0].name,
                    query,
                )
                return IconChoice(name=candidates[0].name, how="fallback")
            # Reserve the slot before the await, so parallel scenes can't exceed the cap.
            job.icons_generated.append(new.name)
            try:
                icon = await self.create(
                    new.name, new.subject, new.description, new.tags
                )
            except Exception as exc:
                job.icons_generated.remove(new.name)
                if not candidates:
                    raise
                log.warning(
                    "Drawing icon %r failed (%s); using %r",
                    new.name,
                    exc,
                    candidates[0].name,
                )
                return IconChoice(name=candidates[0].name, how="fallback")
            return IconChoice(name=icon.name, how="generated")

    async def icons_for_scene(
        self, slots: dict, scene_title: str, narration: str, job: Job
    ) -> dict[str, str]:
        """{icon_query: "icons/<name>.svg"} for every icon a scene uses."""
        result = {}
        for query, label in icon_queries(slots):
            context = IconContext(
                scene_title=scene_title, label=label, narration=narration
            )
            choice = await self.pick(query, context, job)
            result[query] = icon_path(choice.name)
        return result


def new_icon_from_seed(line: str) -> NewIcon:
    """Parse a seed_list.txt line: `name | subject | tag, tag, tag`."""
    name, subject, tags = (part.strip() for part in line.split("|"))
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return NewIcon(
        name=name,
        subject=subject,
        description=f"{subject[0].upper()}{subject[1:]}.",
        tags=tag_list[:6] if len(tag_list) >= 3 else [*tag_list, name, subject][:3],
    )
