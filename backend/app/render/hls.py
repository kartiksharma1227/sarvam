"""Live HLS stream: each scene is cut into segments as soon as it renders, and a growing playlist
lists them strictly in scene order, so playback can start while later scenes are still rendering.

Every scene MP4 has identical encode settings (renderer/server/render-core.js ENCODE), so the
segments are copied, not re-encoded. Scenes are joined with #EXT-X-DISCONTINUITY.
"""

import asyncio
import os
import re
from collections.abc import Callable
from pathlib import Path

from app.config import settings
from app.ffmpeg import run_ffmpeg
from app.models.job import Job, Segment

PLAYLIST_NAME = "stream.m3u8"
# Fixed for the whole stream: an EVENT playlist must not change it once published.
# Scenes have a keyframe every second, so 4 s segments stay well under this.
TARGET_DURATION = 6


def segment_scene(mp4: Path, hls_dir: Path, name: str) -> list[Segment]:
    """Cut one scene MP4 into HLS segments (`<name>_000.ts`, ...). Blocking: call in a thread."""
    hls_dir.mkdir(parents=True, exist_ok=True)
    scene_playlist = hls_dir / f"{name}.m3u8"
    run_ffmpeg(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(mp4),
            "-c",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            str(settings.hls_segment_seconds),
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(hls_dir / f"{name}_%03d.ts"),
            str(scene_playlist),
        ]
    )
    return parse_segments(scene_playlist.read_text())


def parse_segments(playlist: str) -> list[Segment]:
    segments, duration = [], None
    for line in playlist.splitlines():
        line = line.strip()
        if match := re.match(r"#EXTINF:([\d.]+)", line):
            duration = float(match.group(1))
        elif line and not line.startswith("#") and duration is not None:
            segments.append(Segment(uri=line, duration=duration))
            duration = None
    if not segments:
        raise ValueError("ffmpeg produced no HLS segments")
    return segments


def render_playlist(scenes: list[list[Segment]], ended: bool) -> str:
    """The master playlist for these scenes, in order."""
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{TARGET_DURATION}",
        "#EXT-X-PLAYLIST-TYPE:EVENT",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]
    for n, segments in enumerate(scenes):
        if n > 0:
            lines.append("#EXT-X-DISCONTINUITY")
        for segment in segments:
            if round(segment.duration) > TARGET_DURATION:
                raise ValueError(
                    f"segment {segment.uri} is {segment.duration:.1f}s, over the {TARGET_DURATION}s target"
                )
            lines += [f"#EXTINF:{segment.duration:.3f},", segment.uri]
    if ended:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """Players polling the playlist never see a half-written file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class StreamWriter:
    """Adds scenes to the job's playlist as they become ready, never out of order.

    A scene is ready once it has segments. Only the contiguous run of ready scenes from scene 1 is
    published: if scene 3 is ready before scene 2, it waits.
    """

    def __init__(
        self,
        job: Job,
        media_root: Path,
        on_stream_ready: Callable[[str], None] = lambda path: None,
    ):
        self.job = job
        self.media_root = media_root
        self.hls_dir = media_root / "jobs" / str(job.id) / "hls"
        self.playlist = self.hls_dir / PLAYLIST_NAME
        self.on_stream_ready = on_stream_ready
        self.published = 0  # scenes currently in the playlist
        self._lock = asyncio.Lock()

    @property
    def playlist_path(self) -> str:
        return self.playlist.relative_to(self.media_root).as_posix()

    def _ready_prefix(self) -> int:
        count = 0
        for scene in self.job.scenes:
            if not scene.segments:
                break
            count += 1
        return count

    async def update(self, ended: bool = False) -> list[int]:
        """Rewrite the playlist with every publishable scene. Returns indexes newly published."""
        async with self._lock:
            ready = self._ready_prefix()
            if ready == self.published and not ended:
                return []
            self.hls_dir.mkdir(parents=True, exist_ok=True)
            text = render_playlist(
                [s.segments for s in self.job.scenes[:ready]],
                ended=ended and ready == len(self.job.scenes),
            )
            write_atomic(self.playlist, text)
            newly = list(range(self.published, ready))
            first_time = self.published == 0 and ready > 0
            self.published = ready
            if first_time:
                self.on_stream_ready(self.playlist_path)
            return newly
