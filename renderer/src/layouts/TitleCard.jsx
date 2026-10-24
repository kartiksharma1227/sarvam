import { measureText } from '@remotion/layout-utils';
import { titleCardLayout } from '../engine/geometry.js';
import { scaledMax, textBlock } from '../engine/textFit.js';
import { FONTS } from '../fonts.js';
import { DrawIcon } from '../primitives/DrawIcon.jsx';
import { HandText } from '../primitives/HandText.jsx';
import { Underline } from '../primitives/Underline.jsx';
import { useCue, useScene } from '../SceneContext.js';
import { COLORS, FONT_SIZES, TIMING } from '../theme.js';

export function TitleCard({ slots }) {
  const { icons, canvas } = useScene();
  const cue = useCue();
  const { heading, subheading, icon_query: iconQuery } = slots;
  const { boxes, headingLines, subheadingLines } = titleCardLayout({ hasIcon: Boolean(iconQuery), hasSubheading: Boolean(subheading) }, canvas);

  const iconT = cue('icon', 0.2);
  const headingT = cue('title', iconQuery ? 0.7 : 0.2);
  const subT = cue('subheading', headingT + 1.0);

  const { width: textWidth, underlineY } = textBlock({
    text: heading,
    box: boxes.heading,
    fontFamily: FONTS.display,
    max: scaledMax(FONT_SIZES.heading, canvas),
    maxLines: headingLines,
    measure: (line, fontSize) => measureText({ text: line, fontFamily: FONTS.display, fontSize }).width,
  });

  return (
    <>
      {iconQuery && <DrawIcon src={icons[iconQuery]} box={boxes.icon} start={iconT} />}
      <HandText text={heading} box={boxes.heading} start={headingT} font="display" max={FONT_SIZES.heading} maxLines={headingLines} duration={0.8} />
      <Underline
        x={boxes.heading.x + (boxes.heading.w - textWidth) / 2}
        y={underlineY}
        width={textWidth}
        start={headingT + 0.8}
        seedKey="heading-underline"
      />
      {subheading && (
        <HandText text={subheading} box={boxes.subheading} start={subT} max={FONT_SIZES.subheading} maxLines={subheadingLines} color={COLORS.muted} duration={TIMING.textWipe * 2} />
      )}
    </>
  );
}
