import { fitText, fitTextOnNLines } from '@remotion/layout-utils';
import { FONT_SIZES, PORTRAIT_FONT_SCALE } from '../theme.js';

// The font-size cap for this canvas: larger on portrait (see PORTRAIT_FONT_SCALE).
export function scaledMax(max, canvas) {
  return canvas && canvas.height > canvas.width ? Math.round(max * PORTRAIT_FONT_SCALE) : max;
}

// Largest font size (capped at `max`) that fits `text` inside a w x h box on up to `maxLines` lines.
export function fitFont({ text, width, height, fontFamily, max, maxLines = 1, min = FONT_SIZES.min }) {
  const lineHeight = 1.15;
  if (maxLines === 1) {
    const { fontSize } = fitText({ text, withinWidth: width, fontFamily });
    return { fontSize: clamp(Math.min(fontSize, height / lineHeight), min, max), lines: [text] };
  }
  // Short text often fits bigger on one line than when sized for `maxLines` lines: use whichever is larger.
  const single = fitFont({ text, width, height, fontFamily, max, maxLines: 1, min });
  const { fontSize, lines } = fitTextOnNLines({
    text,
    maxLines,
    maxBoxWidth: width,
    fontFamily,
    maxFontSize: Math.min(max, height / (maxLines * lineHeight)),
  });
  const wrapped = { fontSize: Math.max(fontSize, min), lines };
  return single.fontSize >= wrapped.fontSize ? single : wrapped;
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// Where a centred, possibly wrapped text block ends up in its box: font size, its widest line and
// the y of its last line's baseline area (for an underline). `measure(line, fontSize)` returns a width.
export function textBlock({ text, box, fontFamily, max, maxLines = 1, measure }) {
  const { fontSize, lines } = fitFont({ text, width: box.w, height: box.h, fontFamily, max, maxLines });
  const lineHeight = fontSize * 1.15;
  const width = Math.min(Math.max(...lines.map((line) => measure(line, fontSize))), box.w);
  const blockH = lines.length * lineHeight;
  const underlineY = box.y + box.h / 2 + blockH / 2 - lineHeight / 2 + fontSize * 0.55;
  return { fontSize, lines, width, underlineY };
}
