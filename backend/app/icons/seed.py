"""Build the starting icon library from seed_list.txt.

    python -m app.icons.seed                     draw every seed icon not in the library yet
    python -m app.icons.seed --limit 5           only the first 5 missing ones (try it out)
    python -m app.icons.seed --redo bank tree    redraw these icons (replaces them in place)
    python -m app.icons.seed --sheet sheet.png   write a contact sheet of the whole library
    python -m app.icons.seed --atlas-index       create the Atlas Vector Search index (Atlas only)

Resumable: icons already in the library are skipped.
"""

import argparse
import asyncio
import math
import time
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import settings
from app.icons.library import VECTOR_INDEX, IconLibrary, new_icon_from_seed
from app.models.icon import Icon

SEED_LIST = Path(__file__).parent / "seed_list.txt"


def read_seed_list() -> list:
    lines = [
        line.strip()
        for line in SEED_LIST.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return [new_icon_from_seed(line) for line in lines]


async def seed(
    library: IconLibrary, limit: int | None, redo: list[str], concurrency: int
):
    entries = read_seed_list()
    existing = set(await library.names())
    if redo:
        unknown = set(redo) - {e.name for e in entries}
        if unknown:
            raise SystemExit(f"Not in seed_list.txt: {', '.join(sorted(unknown))}")
        todo = [e for e in entries if e.name in redo]
    else:
        todo = [e for e in entries if e.name not in existing]
    todo = todo[:limit] if limit else todo
    print(
        f"{len(entries)} seed icons, {len(existing)} already in the library, "
        f"{len(todo)} to draw with {settings.icon_image_model} ({settings.icon_image_quality})."
    )
    if not todo:
        return

    limit_slots = asyncio.Semaphore(concurrency)
    failed = []
    started = time.time()

    async def draw(n: int, entry) -> None:
        async with limit_slots:
            try:
                await library.create(
                    entry.name, entry.subject, entry.description, entry.tags, "seed"
                )
                print(f"  [{n}/{len(todo)}] {entry.name}")
            except Exception as exc:  # noqa: BLE001 - one bad icon must not stop the batch
                failed.append(entry.name)
                print(f"  [{n}/{len(todo)}] {entry.name} FAILED: {str(exc)[:200]}")

    await asyncio.gather(*(draw(n, e) for n, e in enumerate(todo, 1)))
    print(f"\nDrew {len(todo) - len(failed)} icons in {time.time() - started:.0f}s.")
    for model, use in library.llm.usage.by_model.items():
        print(
            f"  {model}: {use['calls']} calls, {use['input_tokens']} in / {use['output_tokens']} out tokens"
        )
    if failed:
        print(f"Failed (re-run to retry): {', '.join(failed)}")


def contact_sheet(
    media_root: Path, icons: list[Icon], out: Path, cell: int = 180
) -> None:
    columns = 10
    rows = math.ceil(len(icons) / columns)
    sheet = Image.new("RGB", (columns * cell, rows * (cell + 24)), "#fbfaf7")
    draw = ImageDraw.Draw(sheet)
    for n, icon in enumerate(icons):
        x, y = (n % columns) * cell, (n // columns) * (cell + 24)
        image = Image.open(media_root / icon.png_path).convert("RGBA")
        image.thumbnail((cell - 20, cell - 20))
        sheet.paste(image, (x + 10, y + 10), image)
        draw.text((x + 10, y + cell), icon.name, fill="#1f1f1f")
    sheet.save(out)
    print(f"Contact sheet of {len(icons)} icons -> {out}")


async def create_atlas_index() -> None:
    from pymongo.operations import SearchIndexModel

    model = SearchIndexModel(
        name=VECTOR_INDEX,
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": settings.embedding_dimensions,
                    "similarity": "cosine",
                }
            ]
        },
    )
    await Icon.get_pymongo_collection().create_search_index(model)
    print(
        f"Created Atlas Vector Search index {VECTOR_INDEX!r} (it takes a minute to build)."
    )


async def main(args) -> None:
    from app.agents.llm import get_llm
    from app.db import init_db
    from app.icons.embed import OpenAIEmbedder
    from app.icons.generate import ImageGenerator

    client = await init_db()
    try:
        media_root = settings.media_dir.resolve()
        if args.atlas_index:
            await create_atlas_index()
            return
        library = IconLibrary(get_llm(), OpenAIEmbedder(), ImageGenerator(), media_root)
        if not args.sheet or args.limit or args.redo:
            await seed(library, args.limit, args.redo, args.concurrency)
        if args.sheet:
            icons = await Icon.find_all().sort("+name").to_list()
            contact_sheet(media_root, icons, Path(args.sheet))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m app.icons.seed")
    parser.add_argument("--limit", type=int, help="draw at most this many icons")
    parser.add_argument("--redo", nargs="+", default=[], metavar="NAME")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--sheet", metavar="PNG", help="write a contact sheet")
    parser.add_argument("--atlas-index", action="store_true")
    asyncio.run(main(parser.parse_args()))
