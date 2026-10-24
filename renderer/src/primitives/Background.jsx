import { AbsoluteFill } from 'remotion';
import { COLORS } from '../theme.js';

const GRID = 48;

export function Background({ kind = 'plain' }) {
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.paper }}>
      {kind === 'graph_paper' && (
        <svg width="100%" height="100%">
          <defs>
            <pattern id="grid" width={GRID} height={GRID} patternUnits="userSpaceOnUse">
              <path d={`M ${GRID} 0 L 0 0 0 ${GRID}`} fill="none" stroke={COLORS.grid} strokeWidth={1.5} />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      )}
    </AbsoluteFill>
  );
}
