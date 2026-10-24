import { useMemo } from 'react';
import { vennLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { RoughPaths } from '../primitives/RoughPaths.jsx';
import { generator, roughOptions, toPaths } from '../primitives/rough.js';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS } from '../theme.js';

// Translucent fills, so the overlap reads as a mix of both.
const FILLS = { left: `${COLORS.blue}40`, right: `${COLORS.yellow}55` };

// Cues: "left", "right" (each circle + its icon and label), "both" (the overlap label).
export function Venn({ slots }) {
  const { icons, canvas, sceneId } = useScene();
  const cue = useCue();
  const { left, right, both } = slots;
  const { boxes, circles } = vennLayout(canvas);
  const times = { left: cue('left', 0.6), right: cue('right', 2.0) };
  const bothT = cue('both', times.right + 1.4);
  const sides = { left, right };

  const circlePaths = useMemo(
    () =>
      ['left', 'right'].map((side, i) => {
        const { cx, cy, r } = circles[i];
        const opts = roughOptions(sceneId, `venn.${side}`, { fill: FILLS[side], fillStyle: 'solid', roughness: 1.1 });
        return toPaths(generator.ellipse(cx, cy, r * 2, r * 2, opts));
      }),
    [sceneId, circles],
  );

  return (
    <>
      {['left', 'right'].map((side, i) => {
        const t = times[side];
        return (
          <div key={side}>
            <RoughPaths paths={circlePaths[i]} start={Math.max(0, t - 0.25)} duration={0.6} />
            <DrawIcon src={icons[sides[side].icon_query]} box={boxes[`${side}.icon`]} start={t} />
            <HandText text={sides[side].label} box={boxes[`${side}.label`]} start={t + 0.2} font="display" max={60} maxLines={2} />
          </div>
        );
      })}
      <HandText text={both.label} box={boxes['both.label']} start={bothT} font="display" max={52} maxLines={2} color={COLORS.ink} />
    </>
  );
}
