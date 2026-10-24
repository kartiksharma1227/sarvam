import { createContext, useContext } from 'react';
import { cueTime } from './engine/timing.js';

// Per-scene data every layout and primitive needs: cues, icon URLs, fps, scene id (for seeds).
export const SceneContext = createContext(null);

export function useScene() {
  const ctx = useContext(SceneContext);
  if (!ctx) throw new Error('useScene must be used inside <SceneContext.Provider>');
  return ctx;
}

// Returns cue(target, fallbackSeconds) -> start time in seconds for this scene.
export function useCue() {
  const { cues } = useScene();
  return (target, fallback = 0) => cueTime(cues, target, fallback);
}
