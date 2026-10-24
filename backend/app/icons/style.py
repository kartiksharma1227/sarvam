"""The locked icon style: one prompt and one palette for every icon, so the whole library looks alike.

Bump STYLE_VERSION when either changes; icons keep the version they were drawn with.
"""

STYLE_VERSION = 1

STYLE_PROMPT = (
    "Draw exactly ONE {subject}, as a single icon. "
    "Style: hand-drawn whiteboard doodle, like a marker sketch in an explainer video. "
    "Thick, slightly wobbly black marker outlines of even width. "
    "Flat solid colour fills with no gradients, no shading, no highlights, no shadows and no glow. "
    "Keep colours few and simple, chosen from a limited palette of medium blue, sunny yellow, orange, "
    "leaf green, tomato red, light grey and white. "
    "No text, letters or numbers. No background, no frame, no ground line. "
    "The object is centred and fills most of the square canvas."
)

# Every pixel of a generated icon is snapped to one of these, so icons share exact colours
# with each other and with the renderer theme (renderer/src/theme.js).
PALETTE = {
    "ink": "#1f1f1f",
    "white": "#ffffff",
    "light_grey": "#e5e5e5",
    "grey": "#9ca3af",
    "blue": "#3b82c4",
    "light_blue": "#cfe3f5",
    "yellow": "#f5c518",
    "light_yellow": "#fde68a",
    "orange": "#f08c2e",
    "green": "#7cc35a",
    "light_green": "#c9e8b5",
    "red": "#e5533d",
    "pink": "#f4a7a0",
    "brown": "#9a6a3a",
    "peach": "#f6c9a0",
    "purple": "#8e6cc4",
}


def icon_prompt(subject: str) -> str:
    return STYLE_PROMPT.format(subject=subject)
