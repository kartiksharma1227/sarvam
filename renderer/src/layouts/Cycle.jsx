import { cycleLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { RoughArrow } from '../primitives/RoughArrow.jsx';
import { useCue, useScene } from '../SceneContext.js';
import { FONT_SIZES } from '../theme.js';

// Arrows into a node start this long before the node's word, so the node itself lands on the word.
const ARROW_LEAD = 0.35;

// Cues: "nodes.i". Each node draws on its cue with the arc into it starting just before;
// the closing arc draws after the last node.
export function Cycle({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { nodes } = slots;
  const { boxes, arcs } = cycleLayout(nodes.length, canvas);
  const times = nodes.map((_, i) => cue(`nodes.${i}`, 0.6 + i * 1.4));
  const arcStart = (i) =>
    i < nodes.length - 1 ? Math.max(times[i] + 0.2, times[i + 1] - ARROW_LEAD) : times[nodes.length - 1] + 0.9;

  return (
    <>
      {arcs.map((points, i) => (
        <RoughArrow key={`arc${i}`} points={points} start={arcStart(i)} seedKey={`arc.${i}`} />
      ))}
      {nodes.map((node, i) => {
        const t = times[i];
        return (
          <div key={i}>
            <DrawIcon src={icons[node.icon_query]} box={boxes[`nodes.${i}.icon`]} start={t} />
            <HandText text={node.label} box={boxes[`nodes.${i}.label`]} start={t + 0.2} font="display" max={FONT_SIZES.label} />
          </div>
        );
      })}
    </>
  );
}
