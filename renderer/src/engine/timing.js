// Frame/cue helpers. Pure: no React, no Remotion.

export function secToFrame(seconds, fps) {
  return Math.round(seconds * fps);
}

// Start time (seconds) of a cue target such as "nodes.1"; `fallback` when the cue is missing.
export function cueTime(cues, target, fallback = 0) {
  const cue = (cues || []).find((c) => c.target === target);
  return cue ? cue.start : fallback;
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

// 0 -> 1 progress of an animation that starts at `start` seconds and lasts `duration` seconds.
export function progressAt(frame, fps, start, duration) {
  const t = (frame / fps - start) / duration;
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return easeInOutCubic(t);
}
