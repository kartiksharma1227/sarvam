import { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { fitFont, scaledMax } from '../engine/textFit.js';
import { progressAt } from '../engine/timing.js';
import { FONTS } from '../fonts.js';
import { useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES, TIMING } from '../theme.js';

const JUSTIFY = { left: 'flex-start', center: 'center', right: 'flex-end' };

// Text that fits its box and is revealed with a left-to-right wipe, like writing.
export function HandText({
  text,
  box,
  start,
  font = 'label',
  max = FONT_SIZES.label,
  maxLines = 1,
  color = COLORS.ink,
  align = 'center',
  duration = TIMING.textWipe,
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { canvas } = useScene();
  const fontFamily = FONTS[font];
  const cap = scaledMax(max, canvas);
  const { fontSize, lines } = useMemo(
    () => fitFont({ text, width: box.w, height: box.h, fontFamily, max: cap, maxLines }),
    [text, box.w, box.h, fontFamily, cap, maxLines],
  );

  const p = progressAt(frame, fps, start, duration);
  if (p === 0 || !text) return null;

  return (
    <div
      style={{
        position: 'absolute',
        left: box.x,
        top: box.y,
        width: box.w,
        height: box.h,
        display: 'flex',
        alignItems: 'center',
        justifyContent: JUSTIFY[align],
      }}
    >
      <div
        style={{
          fontFamily,
          fontSize,
          lineHeight: 1.15,
          color,
          textAlign: align,
          whiteSpace: 'nowrap',
          clipPath: `inset(-20% ${(1 - p) * 100}% -20% 0)`,
        }}
      >
        {lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );
}
