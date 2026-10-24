import rough from 'roughjs';
import { COLORS, STROKE } from '../theme.js';
import { seedFrom } from '../engine/seed.js';

const generator = rough.generator();

// Rough.js options with a seed derived from scene id + element key, so output never changes between renders.
export function roughOptions(sceneId, key, extra = {}) {
  return {
    seed: seedFrom(`${sceneId}:${key}`),
    roughness: 1.3,
    bowing: 1.2,
    stroke: COLORS.ink,
    strokeWidth: STROKE.ink,
    ...extra,
  };
}

export function toPaths(drawable) {
  return generator.toPaths(drawable);
}

export { generator };
