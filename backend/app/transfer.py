"""Move the icon library (and the voice-preview cache) from one install to another.

    python -m app.transfer export data.tar.gz    on the machine that has the icons
    python -m app.transfer import data.tar.gz    on the new one (e.g. inside the backend container)

The archive holds icons.jsonl (the `icons` collection, embeddings included) and the files under
MEDIA_DIR/icons and MEDIA_DIR/voices. Importing again is safe: icons are matched by name.
"""

import argparse
import asyncio
import io
import tarfile
from pathlib import Path

from bson import json_util

from app.config import settings
from app.db import init_db
from app.models.icon import Icon

RECORDS = "icons.jsonl"
MEDIA = "media/"
FOLDERS = ("icons", "voices")


async def export_data(out: Path, media_root: Path) -> int:
    """Write the archive; returns how many icon records it holds."""
    docs = await Icon.get_pymongo_collection().find().sort("name").to_list()
    lines = "".join(json_util.dumps(doc) + "\n" for doc in docs).encode()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        info = tarfile.TarInfo(RECORDS)
        info.size = len(lines)
        tar.addfile(info, io.BytesIO(lines))
        for folder in FOLDERS:
            if (media_root / folder).is_dir():
                tar.add(media_root / folder, arcname=MEDIA + folder)
    return len(docs)


async def import_data(archive: Path, media_root: Path) -> tuple[int, int]:
    """Restore the archive; returns (icon records upserted, files written)."""
    collection = Icon.get_pymongo_collection()
    with tarfile.open(archive, "r:gz") as tar:
        records = tar.extractfile(RECORDS)
        if records is None:
            raise ValueError(
                f"{archive} has no {RECORDS}; is it an export from app.transfer?"
            )
        icons = 0
        for line in records.read().decode().splitlines():
            doc = json_util.loads(line)
            # Keep the target's own id if the icon is already there.
            doc.pop("_id", None)
            await collection.replace_one({"name": doc["name"]}, doc, upsert=True)
            icons += 1

        files = []
        for member in tar.getmembers():
            if member.name.startswith(MEDIA) and member.isfile():
                member.name = member.name.removeprefix(MEDIA)
                files.append(member)
        media_root.mkdir(parents=True, exist_ok=True)
        # The "data" filter refuses absolute paths, "..", links and device files.
        tar.extractall(media_root, members=files, filter="data")
    return icons, len(files)


async def main(args) -> None:
    client = await init_db()
    media_root = settings.media_dir.resolve()
    try:
        if args.command == "export":
            count = await export_data(args.archive, media_root)
            print(f"Exported {count} icons and the media files to {args.archive}")
        else:
            icons, files = await import_data(args.archive, media_root)
            print(f"Imported {icons} icons and {files} files into {media_root}")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["export", "import"])
    parser.add_argument("archive", type=Path, help="the .tar.gz to write or read")
    asyncio.run(main(parser.parse_args()))
