import { scaleLayout } from '../engine/geometry.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { HighlightUnder, hasDigit } from '../primitives/HighlightUnder.jsx';
import { RoughBox } from '../primitives/RoughBox.jsx';
import { RoughPaths } from '../primitives/RoughPaths.jsx';
import { generator, roughOptions, toPaths } from '../primitives/rough.js';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES } from '../theme.js';

function parseRange(range) {
  const m = /(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)/.exec(range || '');
  return m ? [Number(m[1]), Number(m[2])] : null;
}

// Position of `value` along the bands (x on landscape, y on portrait), or null if no band range contains it.
function markerPosition(value, bands, rects, axis) {
  for (let i = 0; i < bands.length; i++) {
    const r = parseRange(bands[i].range);
    if (r && value >= r[0] && value <= r[1]) {
      const frac = r[1] === r[0] ? 0.5 : (value - r[0]) / (r[1] - r[0]);
      return axis === 'x' ? rects[i].x + rects[i].w * frac : rects[i].y + rects[i].h * frac;
    }
  }
  return null;
}

// Cues: "stat", "bands.i", "marker".
export function Scale({ slots }) {
  const { icons, canvas, sceneId } = useScene();
  const cue = useCue();
  const { stat, bands, marker_value: markerValue } = slots;
  const { boxes, bandRects, markerAxis } = scaleLayout(bands.length, { hasStat: Boolean(stat), hasStatIcon: Boolean(stat?.icon_query) }, canvas);

  const statT = cue('stat', 0.6);
  const bandTimes = bands.map((_, i) => cue(`bands.${i}`, (stat ? statT + 1.2 : 0.6) + i * 0.6));
  const markerT = cue('marker', bandTimes[bandTimes.length - 1] + 0.9);

  const pos = markerValue == null ? null : markerPosition(Number(markerValue), bands, bandRects, markerAxis);
  const lane = boxes.marker;
  // A triangle in the marker lane pointing at the value: down onto the bands, or right on portrait.
  const triangle =
    pos == null
      ? null
      : markerAxis === 'x'
        ? [[pos - 20, lane.y + 4], [pos + 20, lane.y + 4], [pos, lane.y + lane.h - 2]]
        : [[lane.x + 4, pos - 20], [lane.x + 4, pos + 20], [lane.x + lane.w - 2, pos]];
  const markerPaths = triangle
    ? toPaths(generator.polygon(triangle, roughOptions(sceneId, 'marker', { fill: COLORS.ink, fillStyle: 'solid', roughness: 0.8 })))
    : null;
  const bandAlign = markerAxis === 'x' ? 'center' : 'left';

  return (
    <>
      {stat && (
        <>
          {stat.icon_query && <DrawIcon src={icons[stat.icon_query]} box={boxes['stat.icon']} start={Math.max(0, statT - 0.3)} />}
          <HandText text={stat.value} box={boxes['stat.value']} start={statT} font="display" max={110} />
          {hasDigit(stat.value) && <HighlightUnder text={stat.value} box={boxes['stat.value']} max={110} start={statT + 0.5} seedKey="scale-stat-hl" />}
          <HandText text={stat.caption} box={boxes['stat.caption']} start={statT + 0.4} max={FONT_SIZES.caption} maxLines={markerAxis === 'x' ? 1 : 2} color={COLORS.muted} />
        </>
      )}
      {bands.map((band, i) => (
        <div key={i}>
          <RoughBox box={bandRects[i]} fill={COLORS[band.color] || COLORS.blue} start={bandTimes[i]} seedKey={`band.${i}`} />
          <HandText text={band.label} box={boxes[`bands.${i}.label`]} start={bandTimes[i] + 0.25} font="display" max={42} align={bandAlign} />
          <HandText text={band.range} box={boxes[`bands.${i}.range`]} start={bandTimes[i] + 0.35} max={FONT_SIZES.caption} color={COLORS.muted} align={bandAlign} />
        </div>
      ))}
      {markerPaths && <RoughPaths paths={markerPaths} start={markerT} duration={0.3} />}
    </>
  );
}
