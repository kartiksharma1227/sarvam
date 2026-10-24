import { checklistLayout } from '../engine/geometry.js';
import { Checkmark } from '../primitives/Checkmark.jsx';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { useCue, useScene } from '../SceneContext.js';

// Cues: "items.i" (icon + text), optional "items.i.check" (defaults to shortly after).
export function Checklist({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { items } = slots;
  const { boxes, textLines } = checklistLayout(items.length, canvas);

  return (
    <>
      {items.map((item, i) => {
        const t = cue(`items.${i}`, 0.6 + i * 1.5);
        return (
          <div key={i}>
            <DrawIcon src={icons[item.icon_query]} box={boxes[`items.${i}.icon`]} start={t} />
            <HandText text={item.text} box={boxes[`items.${i}.text`]} start={t + 0.15} font="display" max={58} maxLines={textLines} align="left" />
            <Checkmark box={boxes[`items.${i}.check`]} start={cue(`items.${i}.check`, t + 0.8)} seedKey={`check.${i}`} />
          </div>
        );
      })}
    </>
  );
}
