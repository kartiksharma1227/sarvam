import { useCurrentFrame, useVideoConfig } from 'remotion';
import { progressAt } from '../engine/timing.js';
import { TIMING } from '../theme.js';

const isFill = (p) => p.fill && p.fill !== 'none';

// Draws Rough.js path data: outlines trace on (pathLength trick), fills fade in near the end.
export function RoughPaths({ paths, start, duration = TIMING.shape, opacity = 1 }) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const draw = progressAt(frame, fps, start, duration);
  const fill = progressAt(frame, fps, start + duration * 0.6, TIMING.iconFill);
  if (draw === 0) return null;

  const fills = paths.filter(isFill);
  const strokes = paths.filter((p) => !isFill(p));
  return (
    <svg width={width} height={height} style={{ position: 'absolute', inset: 0, opacity }}>
      {fills.map((p, i) => (
        <path key={`f${i}`} d={p.d} fill={p.fill} stroke="none" opacity={fill} />
      ))}
      {strokes.map((p, i) => (
        <path
          key={`s${i}`}
          d={p.d}
          fill="none"
          stroke={p.stroke}
          strokeWidth={p.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray="1 1"
          strokeDashoffset={1 - draw}
        />
      ))}
    </svg>
  );
}
