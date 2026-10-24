import { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { barChartLayout } from '../engine/geometry.js';
import { progressAt } from '../engine/timing.js';
import { HandText } from '../primitives/HandText.jsx';
import { HighlightUnder } from '../primitives/HighlightUnder.jsx';
import { RoughPaths } from '../primitives/RoughPaths.jsx';
import { generator, roughOptions, toPaths } from '../primitives/rough.js';
import { useCue, useScene } from '../SceneContext.js';
import { BAR_COLORS, COLORS, FONT_SIZES } from '../theme.js';

const GROW_SECONDS = 0.6;

// A bar that grows from the axis (up on landscape, rightwards on portrait) starting at `start`.
function GrowingBar({ rect, color, start, seedKey, vertical }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { sceneId } = useScene();
  const paths = useMemo(
    () => toPaths(generator.rectangle(rect.x, rect.y, rect.w, rect.h, roughOptions(sceneId, seedKey, { fill: color, fillStyle: 'solid' }))),
    [sceneId, seedKey, color, rect.x, rect.y, rect.w, rect.h],
  );
  const grow = progressAt(frame, fps, start, GROW_SECONDS);
  if (grow === 0) return null;
  const origin = vertical ? `${rect.x}px ${rect.y + rect.h}px` : `${rect.x}px ${rect.y}px`;
  const transform = vertical ? `scaleY(${grow})` : `scaleX(${grow})`;
  return (
    <div style={{ position: 'absolute', inset: 0, transformOrigin: origin, transform }}>
      <RoughPaths paths={paths} start={start} duration={0.3} />
    </div>
  );
}

// Cues: "bars.i". Each bar grows on its cue; its value writes on above (or beside) it with a highlighter.
export function BarChart({ slots }) {
  const { canvas, sceneId } = useScene();
  const cue = useCue();
  const { bars, caption } = slots;
  const layout = barChartLayout(bars.map((b) => Number(b.value)), { hasCaption: Boolean(caption) }, canvas);
  const { boxes, axis, orientation, labelAlign, captionLines } = layout;
  const vertical = orientation === 'vertical';
  const times = bars.map((_, i) => cue(`bars.${i}`, 0.9 + i * 0.9));
  const axisT = Math.max(0, times[0] - 0.6);
  const axisPaths = toPaths(generator.line(axis.x1, axis.y1, axis.x2, axis.y2, roughOptions(sceneId, 'axis')));
  const valueAlign = vertical ? 'center' : 'left';

  return (
    <>
      <RoughPaths paths={axisPaths} start={axisT} duration={0.5} />
      {bars.map((bar, i) => {
        const t = times[i];
        return (
          <div key={i}>
            <HandText text={bar.label} box={boxes[`bars.${i}.label`]} start={Math.max(0, t - 0.2)} max={FONT_SIZES.label} maxLines={vertical ? 1 : 2} align={labelAlign} />
            <GrowingBar rect={layout.bars[i]} color={COLORS[BAR_COLORS[i % BAR_COLORS.length]]} start={t} seedKey={`bar.${i}`} vertical={vertical} />
            <HandText text={bar.display} box={boxes[`bars.${i}.value`]} start={t + GROW_SECONDS} font="display" max={FONT_SIZES.value} align={valueAlign} />
            <HighlightUnder text={bar.display} box={boxes[`bars.${i}.value`]} max={FONT_SIZES.value} align={valueAlign} start={t + GROW_SECONDS + 0.4} seedKey={`bar-hl.${i}`} />
          </div>
        );
      })}
      {caption && (
        <HandText text={caption} box={boxes.caption} start={times[times.length - 1] + 1.0} max={FONT_SIZES.caption} maxLines={captionLines} color={COLORS.muted} />
      )}
    </>
  );
}
