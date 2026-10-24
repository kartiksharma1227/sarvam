import { measureText } from '@remotion/layout-utils';
import { useEffect, useMemo, useState } from 'react';
import { AbsoluteFill, Easing, Html5Audio, Sequence, cancelRender, continueRender, delayRender, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { titleBox, titleLines } from './engine/geometry.js';
import { scaledMax, textBlock } from './engine/textFit.js';
import { FONTS, waitForFonts } from './fonts.js';
import { LAYOUTS } from './layouts/index.js';
import { Background } from './primitives/Background.jsx';
import { HandText } from './primitives/HandText.jsx';
import { Underline } from './primitives/Underline.jsx';
import { SceneContext, useCue, useScene } from './SceneContext.js';
import { FONT_SIZES } from './theme.js';

function SceneTitle({ title }) {
  const { canvas } = useScene();
  const cue = useCue();
  const box = titleBox(canvas);
  const maxLines = titleLines(canvas);
  const t = cue('title', 0.2);
  const { width, underlineY } = textBlock({
    text: title,
    box,
    fontFamily: FONTS.display,
    max: scaledMax(FONT_SIZES.title, canvas),
    maxLines,
    measure: (line, fontSize) => measureText({ text: line, fontFamily: FONTS.display, fontSize }).width,
  });

  return (
    <>
      <HandText text={title} box={box} start={t} font="display" max={FONT_SIZES.title} maxLines={maxLines} duration={0.7} />
      <Underline x={box.x + (box.w - width) / 2} y={underlineY} width={width} start={t + 0.7} seedKey="title-underline" />
    </>
  );
}

// A slow, eased push-in over the whole scene. 3.5% stays inside the 96 px safe margin, so nothing is cropped.
export const PUSH_IN = 0.035;

export function pushInScale(frame, durationInFrames) {
  return interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [1, 1 + PUSH_IN], {
    easing: Easing.inOut(Easing.sin),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
}

// One scene of a video: background, title, layout, narration. Props follow the RenderProps contract.
export function Scene({ scene, icons = {}, cues = [], audio = null, options = {} }) {
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();
  const zoom = options.zoom === false ? 1 : pushInScale(frame, durationInFrames);
  const [fontsReady, setFontsReady] = useState(false);
  const [handle] = useState(() => delayRender('Loading fonts'));

  useEffect(() => {
    waitForFonts()
      .then(() => {
        setFontsReady(true);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [handle]);

  const Layout = LAYOUTS[scene.layout];
  if (!Layout) throw new Error(`Unknown layout "${scene.layout}"`);

  const ctx = useMemo(
    () => ({ sceneId: scene.id, cues, icons, canvas: { width, height } }),
    [scene.id, cues, icons, width, height],
  );

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${zoom})`, transformOrigin: '50% 50%' }}>
        <Background kind={options.background} />
        {fontsReady && (
          <SceneContext.Provider value={ctx}>
            {scene.layout !== 'title_card' && <SceneTitle title={scene.title} />}
            <Layout slots={scene.slots} scene={scene} />
          </SceneContext.Provider>
        )}
      </AbsoluteFill>
      {audio && (
        <Sequence from={Math.round((audio.offset || 0) * fps)} layout="none">
          <Html5Audio src={audio.url} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
}
