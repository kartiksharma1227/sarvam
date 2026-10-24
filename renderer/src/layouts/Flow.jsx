import { flowLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { RoughArrow } from '../primitives/RoughArrow.jsx';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

// Arrows into a node start this long before the node's word, so the node itself lands on the word.
const ARROW_LEAD = 0.35;

// Cues: "nodes.i". Each node draws on its cue; the arrow into it starts just before.
export function Flow({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { nodes, arrow_labels: arrowLabels = [] } = slots;
  const { boxes, arrows, labelAlign, labelLines } = flowLayout(nodes.length, canvas);
  const times = nodes.map((_, i) => cue(`nodes.${i}`, 0.6 + i * 1.4));
  const arrowStart = (i) => Math.max(times[i] + 0.2, times[i + 1] - ARROW_LEAD);

  return (
    <>
      {arrows.map((a, i) => (
        <RoughArrow key={`a${i}`} {...a} start={arrowStart(i)} seedKey={`arrow.${i}`} />
      ))}
      {arrowLabels.slice(0, arrows.length).map((label, i) =>
        label ? (
          <HandText key={`al${i}`} text={label} box={boxes[`arrows.${i}.label`]} start={arrowStart(i) + 0.2} max={FONT_SIZES.caption} color={COLORS.muted} align={labelAlign} />
        ) : null,
      )}
      {nodes.map((node, i) => {
        const t = times[i];
        return (
          <div key={i}>
            <DrawIcon src={icons[node.icon_query]} box={boxes[`nodes.${i}.icon`]} start={t} />
            <HandText text={node.label} box={boxes[`nodes.${i}.label`]} start={t + 0.2} font="display" max={FONT_SIZES.label} maxLines={labelLines} align={labelAlign} />
          </div>
        );
      })}
    </>
  );
}
