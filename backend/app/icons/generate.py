"""Drawing new icons: image model -> PNG -> palette-snapped, vectorised SVG.

The SVG is what the renderer animates (DrawIcon traces each shape's outline, then fades its fill in).
"""

import base64
import io
import re
from typing import Protocol

import numpy as np
import vtracer
from openai import AsyncOpenAI
from PIL import Image, ImageFilter
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.agents.llm import Usage, is_transient
from app.config import settings
from app.icons.style import PALETTE, icon_prompt

ICON_SIZE = 512
TRANSPARENT = 255  # palette index used for "no pixel" in the snapped image

_RGB = np.array(
    [[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in PALETTE.values()],
    dtype=np.float32,
)
# Rough perceptual weighting so e.g. dark blue snaps to blue rather than ink.
_WEIGHTS = np.array([0.3, 0.59, 0.11], dtype=np.float32)


class Generator(Protocol):
    async def generate(self, subject: str, usage: Usage) -> bytes: ...


class ImageGenerator:
    """Draws one icon with the OpenAI image API, in the locked style."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.icon_image_timeout_seconds,
            max_retries=0,
        )
        self.model = settings.icon_image_model

    @retry(
        retry=retry_if_exception(is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    async def generate(self, subject: str, usage: Usage) -> bytes:
        response = await self.client.images.generate(
            model=self.model,
            prompt=icon_prompt(subject),
            background="transparent",
            size="1024x1024",
            quality=settings.icon_image_quality,
            output_format="png",
        )
        if response.usage:
            usage.add(
                self.model, response.usage.input_tokens, response.usage.output_tokens
            )
        return base64.b64decode(response.data[0].b64_json)


def _nearest(rgb: np.ndarray) -> np.ndarray:
    """Palette index of the nearest colour for each pixel (..., 3)."""
    diff = rgb[..., None, :].astype(np.float32) - _RGB
    return ((diff**2) * _WEIGHTS).sum(-1).argmin(-1)


def clean_png(png: bytes) -> Image.Image:
    """Trim, square, resize to 512 and snap every pixel to the palette (alpha becomes 0 or 255)."""
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    solid = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    box = solid.getbbox()
    if box is None:
        raise ValueError("generated image is empty (fully transparent)")
    image = image.crop(box)

    side = int(max(image.size) * 1.08)  # a little margin so outlines aren't clipped
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    image = square.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)

    pixels = np.array(image)
    index = np.where(pixels[..., 3] >= 128, _nearest(pixels[..., :3]), TRANSPARENT)
    # A mode filter removes the anti-aliasing fringe (e.g. grey between ink and white).
    index = np.array(
        Image.fromarray(index.astype(np.uint8), "L").filter(ImageFilter.ModeFilter(5))
    )
    out = np.zeros((ICON_SIZE, ICON_SIZE, 4), dtype=np.uint8)
    solid = index != TRANSPARENT
    out[solid, :3] = _RGB[index[solid]].astype(np.uint8)
    out[solid, 3] = 255
    return Image.fromarray(out, "RGBA")


def _snap_hex(match: re.Match) -> str:
    value = match.group(1)
    rgb = np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)])
    return f'fill="{list(PALETTE.values())[int(_nearest(rgb))]}"'


def png_to_svg(png: bytes) -> tuple[bytes, str]:
    """(cleaned PNG bytes, SVG text). Deterministic: the same input always gives the same SVG."""
    image = clean_png(png)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    cleaned = buffer.getvalue()

    svg = vtracer.convert_raw_image_to_svg(
        cleaned,
        img_format="png",
        colormode="color",
        # cutout: shapes don't overlap, so fills fade in cleanly (stacked turns muddy mid-fade)
        hierarchical="cutout",
        mode="spline",
        filter_speckle=6,
        color_precision=8,
        layer_difference=8,
        path_precision=2,
    )
    svg = re.sub(r"<\?xml[^>]*\?>\s*|<!--.*?-->\s*", "", svg)
    svg = svg.replace(
        f'width="{ICON_SIZE}" height="{ICON_SIZE}"',
        f'viewBox="0 0 {ICON_SIZE} {ICON_SIZE}"',
        1,
    )
    # vtracer's colour clustering can drift a shade (#E4E4E5); put every fill back on the palette.
    svg = re.sub(r'fill="#([0-9A-Fa-f]{6})"', _snap_hex, svg)
    return cleaned, svg.strip() + "\n"
