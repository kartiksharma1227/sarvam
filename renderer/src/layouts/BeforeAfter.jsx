import { beforeAfterLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { RoughArrow } from '../primitives/RoughArrow.jsx';
import { RoughBox } from '../primitives/RoughBox.jsx';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

const ARROW_LEAD = 0.5;

// Cues: "before", "after". Each panel (frame, header, icon, caption) draws on its cue;
// the arrow into "after" starts just before it.
export function BeforeAfter({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { before, after, arrow_label: arrowLabel } = slots;
  const { boxes, frames, arrow, arrowLabelAlign } = beforeAfterLayout(canvas);
  const times = { before: cue('before', 0.6), after: cue('after', 3.0) };
  const arrowT = Math.max(times.before + 0.6, times.after - ARROW_LEAD);
  const panels = { before, after };

  return (
    <>
      {['before', 'after'].map((side, i) => {
        const t = times[side];
        const p = panels[side];
        return (
          <div key={side}>
            <RoughBox box={frames[i]} start={Math.max(0, t - 0.3)} seedKey={`frame.${side}`} />
            <HandText text={p.header} box={boxes[`${side}.header`]} start={t} font="display" max={64} />
            <DrawIcon src={icons[p.icon_query]} box={boxes[`${side}.icon`]} start={t + 0.15} />
            <HandText text={p.caption} box={boxes[`${side}.caption`]} start={t + 0.5} max={FONT_SIZES.label} maxLines={2} color={COLORS.muted} />
          </div>
        );
      })}
      <RoughArrow {...arrow} start={arrowT} seedKey="before-after-arrow" />
      {arrowLabel && (
        <HandText text={arrowLabel} box={boxes.arrow_label} start={arrowT + 0.2} max={FONT_SIZES.caption} color={COLORS.muted} align={arrowLabelAlign} />
      )}
    </>
  );
}
