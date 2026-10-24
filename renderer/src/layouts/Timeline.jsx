import { timelineLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { RoughPaths } from '../primitives/RoughPaths.jsx';
import { generator, roughOptions, toPaths } from '../primitives/rough.js';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

// Cues: "line", "events.i".
export function Timeline({ slots }) {
  const { icons, canvas, sceneId } = useScene();
  const cue = useCue();
  const { events } = slots;
  const { boxes, line, ticks, textAlign } = timelineLayout(events.length, canvas);
  const eventTimes = events.map((_, i) => cue(`events.${i}`, 1.2 + i * 1.3));
  // The line always finishes before the first event appears on it.
  const lineT = Math.max(0, Math.min(cue('line', 0.4), eventTimes[0] - 0.8));
  const linePaths = toPaths(generator.line(line.x1, line.y1, line.x2, line.y2, roughOptions(sceneId, 'line')));

  return (
    <>
      <RoughPaths paths={linePaths} start={lineT} duration={0.8} />
      {events.map((event, i) => {
        const t = eventTimes[i];
        const tick = ticks[i];
        const tickPaths = toPaths(generator.line(tick.x1, tick.y1, tick.x2, tick.y2, roughOptions(sceneId, `tick.${i}`)));
        return (
          <div key={i}>
            <RoughPaths paths={tickPaths} start={t} duration={0.2} />
            <HandText text={event.date_label} box={boxes[`events.${i}.date`]} start={t} font="display" max={44} align={textAlign === 'left' ? 'right' : 'center'} />
            <DrawIcon src={icons[event.icon_query]} box={boxes[`events.${i}.icon`]} start={t + 0.1} />
            <HandText text={event.text} box={boxes[`events.${i}.text`]} start={t + 0.3} max={FONT_SIZES.caption} maxLines={2} color={COLORS.ink} align={textAlign} />
          </div>
        );
      })}
    </>
  );
}
