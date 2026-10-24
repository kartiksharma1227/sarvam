import { statLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { HighlightUnder } from '../primitives/HighlightUnder.jsx';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

// Cue: "stat" (the spoken number). The icon leads in just before, the number lands on the cue.
export function Stat({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { value, caption, icon_query: iconQuery } = slots;
  const { boxes, captionLines } = statLayout(canvas);
  const t = cue('stat', 0.6);

  return (
    <>
      <DrawIcon src={icons[iconQuery]} box={boxes.icon} start={Math.max(0, t - 0.3)} />
      <HighlightUnder text={value} box={boxes.value} max={FONT_SIZES.bigValue} start={t + 0.6} seedKey="stat-underline" />
      <HandText text={value} box={boxes.value} start={t} font="display" max={FONT_SIZES.bigValue} />
      <HandText text={caption} box={boxes.caption} start={t + 0.5} max={FONT_SIZES.subheading} maxLines={captionLines} color={COLORS.muted} />
    </>
  );
}
