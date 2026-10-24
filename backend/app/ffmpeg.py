"""Thin wrappers around the ffmpeg / ffprobe command-line tools.

They block, so async pipeline code calls them through `asyncio.to_thread`. Each has a timeout.
"""

import subprocess
import tempfile
from pathlib import Path

from app.config import settings


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=True,
        timeout=settings.ffmpeg_timeout_seconds,
    )


def probe_duration(path: Path) -> float:
    """Media duration in seconds."""
    out = run_ffmpeg(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ]
    )
    return float(out.stdout.strip())


def concat_videos(paths: list[Path], out_path: Path) -> Path:
    """Join MP4s that share identical encode settings, without re-encoding."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as listing:
        listing.write("\n".join(f"file '{p.resolve()}'" for p in paths))
    run_ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing.name,
            "-c",
            "copy",
            str(out_path),
        ]
    )
    Path(listing.name).unlink()
    return out_path


def extract_thumbnail(
    video: Path, out_path: Path, at_seconds: float = 2.0, width: int = 640
) -> Path:
    """Save one frame of `video` as a JPEG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(at_seconds),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            str(out_path),
        ]
    )
    return out_path
