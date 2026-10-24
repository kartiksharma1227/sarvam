import { comparisonLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { HighlightUnder, hasDigit } from '../primitives/HighlightUnder.jsx';
import { RoughPaths } from '../primitives/RoughPaths.jsx';
import { generator, roughOptions, toPaths } from '../primitives/rough.js';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

// Cues: "left", "right" (headers), "rows.r" or "rows.r.left" / "rows.r.right".
// A cell's value (the spoken part) lands on its cue; its icon leads in just before.
export function Comparison({ slots }) {
  const { icons, canvas, sceneId } = useScene();
  const cue = useCue();
  const { left, right, rows } = slots;
  const { boxes, divider } = comparisonLayout(rows.length, canvas);

  const headerT = { left: cue('left', 0.6), right: cue('right', 1.4) };
  const dividerPaths = toPaths(
    generator.line(divider.x1, divider.y1, divider.x2, divider.y2, roughOptions(sceneId, 'divider')),
  );
  const headers = { left, right };

  let lastT = headerT.right;
  const rowTimes = rows.map((_, r) => {
    const leftT = cue(`rows.${r}.left`, cue(`rows.${r}`, lastT + 1.0));
    const rightT = cue(`rows.${r}.right`, leftT + 0.8);
    lastT = rightT;
    return { left: leftT, right: rightT };
  });

  return (
    <>
      <RoughPaths paths={dividerPaths} start={headerT.left} duration={0.6} />
      {['left', 'right'].map((side) => (
        <div key={side}>
          <DrawIcon src={icons[headers[side].icon_query]} box={boxes[`${side}.icon`]} start={headerT[side]} />
          <HandText text={headers[side].header} box={boxes[`${side}.header`]} start={headerT[side] + 0.2} font="display" max={64} align="left" />
          {rows.map((row, r) => {
            const cell = row[side];
            const t = rowTimes[r][side];
            return (
              <div key={r}>
                {cell.icon_query && <DrawIcon src={icons[cell.icon_query]} box={boxes[`rows.${r}.${side}.icon`]} start={Math.max(0, t - 0.2)} />}
                <HandText text={cell.value} box={boxes[`rows.${r}.${side}.value`]} start={t} font="display" max={FONT_SIZES.value} align="left" />
                {hasDigit(cell.value) && (
                  <HighlightUnder text={cell.value} box={boxes[`rows.${r}.${side}.value`]} max={FONT_SIZES.value} align="left" start={t + 0.45} seedKey={`value-hl.${r}.${side}`} />
                )}
                <HandText text={cell.caption} box={boxes[`rows.${r}.${side}.caption`]} start={t + 0.25} max={FONT_SIZES.caption} color={COLORS.muted} align="left" />
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}

