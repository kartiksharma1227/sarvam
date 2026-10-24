import { measureText } from '@remotion/layout-utils';
import { fitFont, scaledMax } from '../engine/textFit.js';
import { FONTS } from '../fonts.js';
import { useScene } from '../SceneContext.js';
import { Underline } from './Underline.jsx';

export const hasDigit = (text) => /\d/.test(text ?? '');

// Yellow highlighter swept under a single line of text that HandText draws in `box`
// (same font fitting, so the stroke matches the text's real width and alignment).
export function HighlightUnder({ text, box, font = 'display', max, align = 'center', start, seedKey }) {
  const { canvas } = useScene();
  if (!text) return null;
  const fontFamily = FONTS[font];
  const { fontSize } = fitFont({ text, width: box.w, height: box.h, fontFamily, max: scaledMax(max, canvas) });
  const width = Math.min(measureText({ text, fontFamily, fontSize }).width, box.w);
  const pad = 10;
  const x =
    align === 'left' ? box.x - pad / 2 : align === 'right' ? box.x + box.w - width - pad / 2 : box.x + (box.w - width) / 2 - pad;
  const y = box.y + box.h / 2 + fontSize * 0.42;
  return <Underline x={x} y={y} width={width + pad} start={start} seedKey={seedKey} />;
}
