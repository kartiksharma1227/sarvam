import { Composition } from 'remotion';
import { Scene } from './Scene.jsx';
import creditScores from './samples/credit-scores.json';
import extraLayouts from './samples/extra-layouts.json';
import newLayouts from './samples/new-layouts.json';
import { CANVAS } from './theme.js';

const AUDIO_TAIL_SECONDS = 0.6;

// Duration comes from the narration (lead-in offset + audio + tail) when present, otherwise the fixed `duration`.
export function calculateMetadata({ props }) {
  const options = props.options || {};
  const fps = options.fps || CANVAS.fps;
  const seconds = props.audio
    ? (props.audio.offset || 0) + props.audio.duration + AUDIO_TAIL_SECONDS
    : props.duration || 6;
  return {
    durationInFrames: Math.ceil(seconds * fps),
    fps,
    width: options.width || CANVAS.width,
    height: options.height || CANVAS.height,
  };
}

const compositionProps = {
  component: Scene,
  calculateMetadata,
  durationInFrames: 180,
  fps: CANVAS.fps,
  width: CANVAS.width,
  height: CANVAS.height,
};

export function Root() {
  return (
    <>
      {/* Used by the render service and scripts: props are always supplied. */}
      <Composition id="Scene" {...compositionProps} defaultProps={creditScores[0]} />
      {/* Studio previews of the samples. */}
      {[...creditScores, ...extraLayouts, ...newLayouts].map((props) => (
        <Composition key={props.scene.id} id={`sample-${props.scene.id}`} {...compositionProps} defaultProps={props} />
      ))}
    </>
  );
}
