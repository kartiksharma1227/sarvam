import { useMemo } from 'react';
import { useScene } from '../SceneContext.js';
import { generator, roughOptions, toPaths } from './rough.js';
import { RoughPaths } from './RoughPaths.jsx';

// Hand-drawn rectangle, optionally filled with a solid colour.
export function RoughBox({ box, fill, start, seedKey }) {
  const { sceneId } = useScene();
  const paths = useMemo(() => {
    const opts = roughOptions(sceneId, seedKey, fill ? { fill, fillStyle: 'solid' } : {});
    return toPaths(generator.rectangle(box.x, box.y, box.w, box.h, opts));
  }, [sceneId, seedKey, fill, box.x, box.y, box.w, box.h]);
  return <RoughPaths paths={paths} start={start} duration={0.45} />;
}
