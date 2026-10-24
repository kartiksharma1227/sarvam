import { useMemo } from 'react';
import { useScene } from '../SceneContext.js';
import { COLORS } from '../theme.js';
import { generator, roughOptions, toPaths } from './rough.js';
import { RoughPaths } from './RoughPaths.jsx';

export function Checkmark({ box, start, seedKey, color = COLORS.green }) {
  const { sceneId } = useScene();
  const paths = useMemo(() => {
    const at = (fx, fy) => [box.x + box.w * fx, box.y + box.h * fy];
    const opts = roughOptions(sceneId, seedKey, { stroke: color, strokeWidth: 10, roughness: 1 });
    return toPaths(generator.linearPath([at(0.1, 0.55), at(0.4, 0.85), at(0.92, 0.12)], opts));
  }, [sceneId, seedKey, color, box.x, box.y, box.w, box.h]);
  return <RoughPaths paths={paths} start={start} duration={0.35} />;
}
