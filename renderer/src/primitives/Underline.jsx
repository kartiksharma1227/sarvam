import { useMemo } from 'react';
import { useScene } from '../SceneContext.js';
import { COLORS } from '../theme.js';
import { generator, roughOptions, toPaths } from './rough.js';
import { RoughPaths } from './RoughPaths.jsx';

// Yellow highlighter stroke under a heading or key number.
export function Underline({ x, y, width, start, seedKey, color = COLORS.yellow }) {
  const { sceneId } = useScene();
  const paths = useMemo(() => {
    const opts = roughOptions(sceneId, seedKey, {
      stroke: color,
      strokeWidth: 14,
      roughness: 0.8,
      bowing: 2,
      disableMultiStroke: true,
    });
    return toPaths(generator.line(x, y, x + width, y + 4, opts));
  }, [sceneId, seedKey, color, x, y, width]);
  return <RoughPaths paths={paths} start={start} duration={0.4} opacity={0.9} />;
}
