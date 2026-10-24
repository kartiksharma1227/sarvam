import { useMemo } from 'react';
import { useScene } from '../SceneContext.js';
import { COLORS, STROKE } from '../theme.js';
import { generator, roughOptions, toPaths } from './rough.js';
import { RoughPaths } from './RoughPaths.jsx';

const HEAD_LENGTH = 30;
const HEAD_SPREAD = (28 * Math.PI) / 180;

// Straight arrow (x1,y1 -> x2,y2) or curved arrow through `points`. Shaft draws first, then the head.
export function RoughArrow({ x1, y1, x2, y2, points, start, seedKey, color = COLORS.ink }) {
  const { sceneId } = useScene();

  const { shaft, head } = useMemo(() => {
    const opts = roughOptions(sceneId, seedKey, { stroke: color, strokeWidth: STROKE.arrow });
    const path = points ?? [[x1, y1], [x2, y2]];
    const shaftDrawable = points
      ? generator.curve(points, opts)
      : generator.line(x1, y1, x2, y2, opts);

    const [tx, ty] = path[path.length - 1];
    const [px, py] = path[path.length - 2];
    const angle = Math.atan2(ty - py, tx - px);
    const wing = (sign) => [
      tx - HEAD_LENGTH * Math.cos(angle + sign * HEAD_SPREAD),
      ty - HEAD_LENGTH * Math.sin(angle + sign * HEAD_SPREAD),
    ];
    const headDrawable = generator.linearPath([wing(1), [tx, ty], wing(-1)], {
      ...opts,
      seed: opts.seed + 1,
    });
    return { shaft: toPaths(shaftDrawable), head: toPaths(headDrawable) };
  }, [sceneId, seedKey, color, x1, y1, x2, y2, points]);

  return (
    <>
      <RoughPaths paths={shaft} start={start} duration={0.35} />
      <RoughPaths paths={head} start={start + 0.3} duration={0.15} />
    </>
  );
}
