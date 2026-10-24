// Deterministic layout engine. Pure functions only: same input -> same boxes.
// Every layout returns { boxes: {key: {x, y, w, h}}, ...extras }.
// `boxes` holds every leaf element; no two boxes may overlap and all must sit inside the area.
// Each layout works on a landscape (16:9, 1920x1080) and a portrait (9:16, 1080x1920) canvas:
// on a portrait canvas, rows of things become columns (flows and timelines run downwards,
// left/right comparisons become top/bottom).

import { CANVAS, SAFE_MARGIN, TITLE_BAND, TITLE_BAND_PORTRAIT } from '../theme.js';

export const LIMITS = {
  flow: { min: 2, max: 4 },
  comparison: { min: 1, max: 3 },
  scale: { min: 2, max: 5 },
  checklist: { min: 2, max: 5 },
  cycle: { min: 3, max: 5 },
  timeline: { min: 3, max: 5 },
  bar_chart: { min: 2, max: 6 },
};

export function isPortrait(canvas = CANVAS) {
  return canvas.height > canvas.width;
}

export function safeArea(canvas = CANVAS) {
  return {
    x: SAFE_MARGIN,
    y: SAFE_MARGIN,
    w: canvas.width - SAFE_MARGIN * 2,
    h: canvas.height - SAFE_MARGIN * 2,
  };
}

function titleBand(canvas) {
  return isPortrait(canvas) ? TITLE_BAND_PORTRAIT : TITLE_BAND;
}

export function titleBox(canvas = CANVAS) {
  const area = safeArea(canvas);
  return { x: area.x, y: area.y, w: area.w, h: titleBand(canvas).height };
}

// Lines the scene title may wrap onto.
export function titleLines(canvas = CANVAS) {
  return isPortrait(canvas) ? 2 : 1;
}

// Region below the title band where layouts place their elements.
export function contentArea(canvas = CANVAS) {
  const area = safeArea(canvas);
  const band = titleBand(canvas);
  const top = area.y + band.height + band.gapBelow;
  return { x: area.x, y: top, w: area.w, h: area.y + area.h - top };
}

export function boxesOverlap(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

export function insideArea(box, area) {
  const eps = 0.001;
  return (
    box.x >= area.x - eps &&
    box.y >= area.y - eps &&
    box.x + box.w <= area.x + area.w + eps &&
    box.y + box.h <= area.y + area.h + eps
  );
}

export function center(box) {
  return { x: box.x + box.w / 2, y: box.y + box.h / 2 };
}

function assertCount(layout, n) {
  const { min, max } = LIMITS[layout];
  if (!Number.isInteger(n) || n < min || n > max) {
    throw new Error(`${layout}: count ${n} outside ${min}-${max}`);
  }
}

function boxAt(cx, y, w, h) {
  return { x: cx - w / 2, y, w, h };
}

// ---------------------------------------------------------------- title card

export function titleCardLayout({ hasIcon = true, hasSubheading = true } = {}, canvas = CANVAS) {
  const area = safeArea(canvas);
  const portrait = isPortrait(canvas);
  const cx = area.x + area.w / 2;
  const iconSize = portrait ? 300 : 240;
  const headingH = portrait ? 320 : 150;
  const subH = portrait ? 160 : 80;
  const gap = portrait ? 50 : 36;

  const total = (hasIcon ? iconSize + gap : 0) + headingH + (hasSubheading ? gap + subH : 0);
  let y = area.y + (area.h - total) / 2;

  const boxes = {};
  if (hasIcon) {
    boxes.icon = boxAt(cx, y, iconSize, iconSize);
    y += iconSize + gap;
  }
  boxes.heading = boxAt(cx, y, Math.min(1600, area.w), headingH);
  y += headingH;
  if (hasSubheading) {
    boxes.subheading = boxAt(cx, y + gap, Math.min(1400, area.w), subH);
  }
  return { area, boxes, headingLines: portrait ? 2 : 1, subheadingLines: portrait ? 2 : 1 };
}

// ---------------------------------------------------------------------- flow

export function flowLayout(n, canvas = CANVAS) {
  assertCount('flow', n);
  const area = contentArea(canvas);
  if (isPortrait(canvas)) {
    // Top to bottom: icon on the left, label to its right, arrows pointing down.
    const rowH = Math.min(360, area.h / n);
    const iconSize = Math.min(220, rowH * 0.55);
    const labelH = 110;
    const top = area.y + (area.h - rowH * n) / 2;
    const iconX = area.x + 30;
    const iconCx = iconX + iconSize / 2;
    const labelX = iconX + iconSize + 40;

    const boxes = {};
    const arrows = [];
    for (let i = 0; i < n; i++) {
      const rowY = top + i * rowH;
      boxes[`nodes.${i}.icon`] = { x: iconX, y: rowY + (rowH - iconSize) / 2, w: iconSize, h: iconSize };
      boxes[`nodes.${i}.label`] = { x: labelX, y: rowY + (rowH - labelH) / 2, w: area.x + area.w - labelX, h: labelH };
    }
    for (let i = 0; i < n - 1; i++) {
      const from = boxes[`nodes.${i}.icon`];
      const to = boxes[`nodes.${i + 1}.icon`];
      const y1 = from.y + from.h + 20;
      const y2 = to.y - 20;
      arrows.push({ x1: iconCx, y1, x2: iconCx, y2 });
      const mid = (y1 + y2) / 2;
      boxes[`arrows.${i}.label`] = { x: iconCx + 30, y: mid - 25, w: area.x + area.w - iconCx - 30, h: 50 };
    }
    return { area, boxes, arrows, labelAlign: 'left', labelLines: 2 };
  }

  const slotW = area.w / n;
  const iconSize = Math.min(240, slotW * 0.5);
  const labelH = 70;
  const labelGap = 24;
  const groupH = iconSize + labelGap + labelH;
  const top = area.y + (area.h - groupH) / 2;

  const boxes = {};
  const arrows = [];
  for (let i = 0; i < n; i++) {
    const cx = area.x + slotW * (i + 0.5);
    boxes[`nodes.${i}.icon`] = boxAt(cx, top, iconSize, iconSize);
    boxes[`nodes.${i}.label`] = boxAt(cx, top + iconSize + labelGap, slotW - 40, labelH);
  }
  for (let i = 0; i < n - 1; i++) {
    const from = boxes[`nodes.${i}.icon`];
    const to = boxes[`nodes.${i + 1}.icon`];
    const y = top + iconSize / 2;
    const x1 = from.x + from.w + 30;
    const x2 = to.x - 30;
    arrows.push({ x1, y1: y, x2, y2: y });
    boxes[`arrows.${i}.label`] = { x: x1, y: y - 80, w: x2 - x1, h: 50 };
  }
  return { area, boxes, arrows, labelAlign: 'center', labelLines: 1 };
}

// ---------------------------------------------------------------- comparison

// One column (side) of a comparison: header row, then `rows` cells (icon, value, caption).
function comparisonColumn(boxes, side, rows, { x, y, w, h }, maxTextW = 400) {
  const headerIcon = 110;
  const rowsTop = y + headerIcon + 30;
  const rowH = (y + h - rowsTop) / rows;
  const iconSize = Math.min(rowH * 0.7, 140);
  const valueH = Math.min(rowH * 0.48, 96);
  const captionH = Math.min(rowH * 0.3, 52);
  const textW = Math.min(maxTextW, w - iconSize - 30);
  const blockW = iconSize + 30 + textW;
  const cx = x + w / 2;

  boxes[`${side}.icon`] = { x: cx - blockW / 2, y, w: headerIcon, h: headerIcon };
  boxes[`${side}.header`] = { x: cx - blockW / 2 + headerIcon + 20, y: y + 15, w: blockW - headerIcon - 20, h: 84 };
  for (let r = 0; r < rows; r++) {
    const rowY = rowsTop + r * rowH;
    const blockX = cx - blockW / 2;
    const textX = blockX + iconSize + 30;
    const textTop = rowY + (rowH - valueH - captionH) / 2;
    boxes[`rows.${r}.${side}.icon`] = { x: blockX, y: rowY + (rowH - iconSize) / 2, w: iconSize, h: iconSize };
    boxes[`rows.${r}.${side}.value`] = { x: textX, y: textTop, w: textW, h: valueH };
    boxes[`rows.${r}.${side}.caption`] = { x: textX, y: textTop + valueH, w: textW, h: captionH };
  }
}

export function comparisonLayout(rows, canvas = CANVAS) {
  assertCount('comparison', rows);
  const area = contentArea(canvas);
  const boxes = {};
  if (isPortrait(canvas)) {
    // Left becomes top, right becomes bottom, with a horizontal divider between them.
    const gap = 60;
    const blockH = (area.h - gap) / 2;
    comparisonColumn(boxes, 'left', rows, { x: area.x, y: area.y, w: area.w, h: blockH }, 560);
    comparisonColumn(boxes, 'right', rows, { x: area.x, y: area.y + blockH + gap, w: area.w, h: blockH }, 560);
    const midY = area.y + blockH + gap / 2;
    return { area, boxes, divider: { x1: area.x, y1: midY, x2: area.x + area.w, y2: midY } };
  }
  const colW = area.w / 2 - 40;
  comparisonColumn(boxes, 'left', rows, { x: area.x, y: area.y, w: colW, h: area.h });
  comparisonColumn(boxes, 'right', rows, { x: area.x + area.w - colW, y: area.y, w: colW, h: area.h });
  const midX = area.x + area.w / 2;
  return { area, boxes, divider: { x1: midX, y1: area.y, x2: midX, y2: area.y + area.h } };
}

// ---------------------------------------------------------------------- stat

export function statLayout(canvas = CANVAS) {
  const area = contentArea(canvas);
  const portrait = isPortrait(canvas);
  const cx = area.x + area.w / 2;
  const iconSize = portrait ? 240 : 200;
  const valueH = portrait ? 260 : 220;
  const captionH = portrait ? 150 : 70;
  const gap = portrait ? 30 : 20;
  let y = area.y + (area.h - (iconSize + valueH + captionH + gap * 2)) / 2;

  const boxes = {};
  boxes.icon = boxAt(cx, y, iconSize, iconSize);
  y += iconSize + gap;
  boxes.value = boxAt(cx, y, Math.min(900, area.w), valueH);
  y += valueH + gap;
  boxes.caption = boxAt(cx, y, Math.min(1200, area.w), captionH);
  return { area, boxes, captionLines: portrait ? 2 : 1 };
}

// --------------------------------------------------------------------- scale

export function scaleLayout(bands, { hasStat = false, hasStatIcon = true } = {}, canvas = CANVAS) {
  assertCount('scale', bands);
  const area = contentArea(canvas);
  const portrait = isPortrait(canvas);
  const cx = area.x + area.w / 2;

  const statIcon = 110;
  const statValueH = 110;
  const statCaptionH = portrait ? 90 : 46;
  const statH = statIcon + 8 + statValueH + 6 + statCaptionH;

  const boxes = {};
  let y;
  if (portrait) {
    // Bands stacked top to bottom; the marker points at the value from a lane on the left.
    const bandsSpace = area.h - (hasStat ? statH + 30 : 0);
    const rowH = Math.min(170, bandsSpace / bands);
    y = area.y + (area.h - (hasStat ? statH + 30 : 0) - rowH * bands) / 2;
    if (hasStat) {
      if (hasStatIcon) boxes['stat.icon'] = boxAt(cx, y, statIcon, statIcon);
      y += statIcon + 8;
      boxes['stat.value'] = boxAt(cx, y, Math.min(700, area.w), statValueH);
      y += statValueH + 6;
      boxes['stat.caption'] = boxAt(cx, y, area.w, statCaptionH);
      y += statCaptionH + 30;
    }
    const laneW = 60;
    const rectX = area.x + laneW + 10;
    const rectW = 320;
    const textX = rectX + rectW + 30;
    const bandRects = [];
    for (let i = 0; i < bands; i++) {
      const rowY = y + i * rowH;
      const rect = { x: rectX, y: rowY, w: rectW, h: rowH - 24 };
      bandRects.push(rect);
      boxes[`bands.${i}.rect`] = rect;
      boxes[`bands.${i}.label`] = { x: textX, y: rowY, w: area.x + area.w - textX, h: rect.h * 0.55 };
      boxes[`bands.${i}.range`] = { x: textX, y: rowY + rect.h * 0.58, w: area.x + area.w - textX, h: rect.h * 0.42 };
    }
    const first = bandRects[0];
    const last = bandRects[bands - 1];
    boxes.marker = { x: area.x, y: first.y, w: laneW, h: last.y + last.h - first.y };
    return { area, boxes, bandRects, markerAxis: 'y' };
  }

  const markerH = 46;
  const bandH = 120;
  const labelH = 50;
  const rangeH = 44;
  const bandsBlockH = bandH + 12 + labelH + 4 + rangeH;
  const total = (hasStat ? statH + 20 : 0) + markerH + 10 + bandsBlockH;

  y = area.y + (area.h - total) / 2;
  if (hasStat) {
    if (hasStatIcon) boxes['stat.icon'] = boxAt(cx, y, statIcon, statIcon);
    y += statIcon + 8;
    boxes['stat.value'] = boxAt(cx, y, 700, statValueH);
    y += statValueH + 6;
    boxes['stat.caption'] = boxAt(cx, y, 900, statCaptionH);
    y += statCaptionH + 20;
  }

  const gap = 24;
  const totalW = Math.min(area.w, bands * 320 + (bands - 1) * gap);
  const bandW = (totalW - (bands - 1) * gap) / bands;
  const left = cx - totalW / 2;

  boxes.marker = { x: left, y, w: totalW, h: markerH };
  y += markerH + 10;

  const bandRects = [];
  for (let i = 0; i < bands; i++) {
    const x = left + i * (bandW + gap);
    const rect = { x, y, w: bandW, h: bandH };
    bandRects.push(rect);
    boxes[`bands.${i}.rect`] = rect;
    boxes[`bands.${i}.label`] = { x, y: y + bandH + 12, w: bandW, h: labelH };
    boxes[`bands.${i}.range`] = { x, y: y + bandH + 12 + labelH + 4, w: bandW, h: rangeH };
  }
  return { area, boxes, bandRects, markerAxis: 'x' };
}

// ----------------------------------------------------------------- checklist

export function checklistLayout(n, canvas = CANVAS) {
  assertCount('checklist', n);
  const area = contentArea(canvas);
  const portrait = isPortrait(canvas);
  const rowH = Math.min(portrait ? 220 : 130, area.h / n);
  const iconSize = Math.min(rowH * 0.78, portrait ? 120 : 100);
  const checkSize = Math.min(rowH * 0.7, 80);
  const textW = Math.min(640, area.w - iconSize - checkSize - 60);
  const blockW = iconSize + 30 + textW + 30 + checkSize;
  const left = area.x + (area.w - blockW) / 2;
  const top = area.y + (area.h - rowH * n) / 2;

  const boxes = {};
  for (let i = 0; i < n; i++) {
    const rowY = top + i * rowH;
    boxes[`items.${i}.icon`] = { x: left, y: rowY + (rowH - iconSize) / 2, w: iconSize, h: iconSize };
    boxes[`items.${i}.text`] = { x: left + iconSize + 30, y: rowY + rowH * 0.2, w: textW, h: rowH * 0.6 };
    boxes[`items.${i}.check`] = {
      x: left + iconSize + 30 + textW + 30,
      y: rowY + (rowH - checkSize) / 2,
      w: checkSize,
      h: checkSize,
    };
  }
  return { area, boxes, textLines: portrait ? 2 : 1 };
}

// --------------------------------------------------------------------- cycle

export function cycleLayout(n, canvas = CANVAS) {
  assertCount('cycle', n);
  const area = contentArea(canvas);
  const portrait = isPortrait(canvas);
  const c = center(area);
  const iconSize = portrait ? 160 : 140;
  const labelH = portrait ? 64 : 46;
  const labelW = 260;
  const groupH = iconSize + 8 + labelH;
  // A wide ellipse on landscape, a tall one on portrait; always inside the content area.
  const rx = Math.min(380, area.w / 2 - labelW / 2 - 12);
  const ry = Math.min(portrait ? 520 : 250, area.h / 2 - groupH / 2 - 12);

  const boxes = {};
  const angles = [];
  const nodeBoxes = [];
  for (let i = 0; i < n; i++) {
    const deg = -90 + (i * 360) / n;
    angles.push(deg);
    const rad = (deg * Math.PI) / 180;
    const px = c.x + rx * Math.cos(rad);
    const py = c.y + ry * Math.sin(rad);
    const top = py - groupH / 2;
    boxes[`nodes.${i}.icon`] = boxAt(px, top, iconSize, iconSize);
    boxes[`nodes.${i}.label`] = boxAt(px, top + iconSize + 8, labelW, labelH);
    nodeBoxes.push({ x: px - labelW / 2, y: top, w: labelW, h: groupH });
  }

  // Arcs follow the ellipse from node i to node i+1, trimmed so they never touch a node.
  const pad = 18;
  const padded = nodeBoxes.map((b) => ({ x: b.x - pad, y: b.y - pad, w: b.w + pad * 2, h: b.h + pad * 2 }));
  const arcs = [];
  for (let i = 0; i < n; i++) {
    const startDeg = angles[i];
    const endDeg = angles[i] + 360 / n;
    const points = [];
    const steps = 48;
    for (let s = 0; s <= steps; s++) {
      const deg = startDeg + ((endDeg - startDeg) * s) / steps;
      const rad = (deg * Math.PI) / 180;
      const p = { x: c.x + rx * Math.cos(rad), y: c.y + ry * Math.sin(rad), w: 0, h: 0 };
      if (!padded.some((b) => insideArea(p, b))) points.push([p.x, p.y]);
    }
    arcs.push(points);
  }
  return { area, boxes, arcs, center: c, rx, ry };
}

// ------------------------------------------------------------------ timeline

export function timelineLayout(n, canvas = CANVAS) {
  assertCount('timeline', n);
  const area = contentArea(canvas);
  const boxes = {};
  const ticks = [];

  if (isPortrait(canvas)) {
    // A vertical line: dates on its left, icon and text on its right, oldest at the top.
    const rowH = Math.min(300, area.h / n);
    const top = area.y + (area.h - rowH * n) / 2;
    const dateW = 170;
    const lineX = area.x + dateW + 30;
    const iconSize = Math.min(120, rowH - 40);
    const textX = lineX + 30 + iconSize + 24;
    const textH = Math.min(rowH - 20, 130);
    for (let i = 0; i < n; i++) {
      const cy = top + rowH * (i + 0.5);
      ticks.push({ x1: lineX - 14, y1: cy, x2: lineX + 14, y2: cy });
      boxes[`events.${i}.date`] = { x: area.x, y: cy - 30, w: dateW, h: 60 };
      boxes[`events.${i}.icon`] = { x: lineX + 30, y: cy - iconSize / 2, w: iconSize, h: iconSize };
      boxes[`events.${i}.text`] = { x: textX, y: cy - textH / 2, w: area.x + area.w - textX, h: textH };
    }
    const line = { x1: lineX, y1: top + 10, x2: lineX, y2: top + rowH * n - 10 };
    return { area, boxes, line, ticks, textAlign: 'left' };
  }

  const iconSize = 130;
  const dateH = 50;
  const textH = 100;
  const lineY = area.y + 14 + iconSize + 14 + dateH + 16 + (area.h - 324) / 2;
  const lineX1 = area.x + 40;
  const lineX2 = area.x + area.w - 40;
  const slotW = (lineX2 - lineX1) / n;
  for (let i = 0; i < n; i++) {
    const cx = lineX1 + slotW * (i + 0.5);
    ticks.push({ x1: cx, y1: lineY - 14, x2: cx, y2: lineY + 14 });
    boxes[`events.${i}.date`] = boxAt(cx, lineY - 16 - dateH, slotW - 30, dateH);
    boxes[`events.${i}.icon`] = boxAt(cx, lineY - 16 - dateH - 14 - iconSize, iconSize, iconSize);
    boxes[`events.${i}.text`] = boxAt(cx, lineY + 24, slotW - 30, textH);
  }
  return { area, boxes, line: { x1: lineX1, y1: lineY, x2: lineX2, y2: lineY }, ticks, textAlign: 'center' };
}

// ---------------------------------------------------------------------- venn

// Two overlapping circles: "left" only, "right" only, and "both" in the overlap.
// On portrait the circles stack vertically (left on top).
export function vennLayout(canvas = CANVAS) {
  const area = contentArea(canvas);
  const c = center(area);
  const boxes = {};
  const iconSize = 120;

  if (isPortrait(canvas)) {
    const r = Math.min(area.w * 0.46, 360);
    const circles = [
      { cx: c.x, cy: c.y - 0.55 * r, r },
      { cx: c.x, cy: c.y + 0.55 * r, r },
    ];
    const labelW = 1.5 * r;
    boxes['left.icon'] = boxAt(c.x, c.y - r - 130, iconSize, iconSize);
    boxes['left.label'] = boxAt(c.x, c.y - r + 10, labelW, 100);
    boxes['both.label'] = boxAt(c.x, c.y - 100, 1.4 * r, 200);
    boxes['right.label'] = boxAt(c.x, c.y + r - 110, labelW, 100);
    boxes['right.icon'] = boxAt(c.x, c.y + r + 10, iconSize, iconSize);
    return { area, boxes, circles };
  }

  const r = Math.min(area.h * 0.46, 330);
  const circles = [
    { cx: c.x - 0.55 * r, cy: c.y, r },
    { cx: c.x + 0.55 * r, cy: c.y, r },
  ];
  // Narrow enough to stay inside its own circle (wrapping to two lines if needed).
  const labelW = Math.min(0.95 * r, 320);
  for (const [side, sign] of [['left', -1], ['right', 1]]) {
    const cx = c.x + sign * r;
    boxes[`${side}.icon`] = boxAt(cx, c.y - iconSize - 10, iconSize, iconSize);
    boxes[`${side}.label`] = boxAt(cx, c.y + 10, labelW, 120);
  }
  boxes['both.label'] = boxAt(c.x, c.y - 70, 0.72 * r, 140);
  return { area, boxes, circles };
}

// ----------------------------------------------------------------- bar chart

// Bars scaled to their values (data, not coordinates). Vertical bars on landscape,
// horizontal bars stacked downwards on portrait. A zero value still shows a sliver.
export function barChartLayout(values, { hasCaption = false } = {}, canvas = CANVAS) {
  assertCount('bar_chart', values.length);
  const area = contentArea(canvas);
  const n = values.length;
  const max = Math.max(...values, 0);
  const frac = (v) => (max > 0 ? Math.max(0, v) / max : 0);
  const boxes = {};
  const bars = [];

  if (isPortrait(canvas)) {
    const captionH = hasCaption ? 120 : 0;
    const chartH = area.h - (hasCaption ? captionH + 20 : 0);
    const rowH = Math.min(200, chartH / n);
    const top = area.y + (chartH - rowH * n) / 2;
    const labelW = 250;
    const x0 = area.x + labelW + 20;
    const valueW = 160;
    const maxW = area.w - labelW - 20 - valueW - 20;
    const barH = Math.min(rowH * 0.55, 90);
    const labelH = Math.min(rowH * 0.7, 110);
    for (let i = 0; i < n; i++) {
      const rowY = top + i * rowH;
      const w = Math.max(8, frac(values[i]) * maxW);
      const rect = { x: x0, y: rowY + (rowH - barH) / 2, w, h: barH };
      bars.push(rect);
      boxes[`bars.${i}.rect`] = rect;
      boxes[`bars.${i}.label`] = { x: area.x, y: rowY + (rowH - labelH) / 2, w: labelW, h: labelH };
      boxes[`bars.${i}.value`] = { x: x0 + w + 12, y: rowY + (rowH - 64) / 2, w: valueW, h: 64 };
    }
    if (hasCaption) boxes.caption = { x: area.x, y: area.y + area.h - captionH, w: area.w, h: captionH };
    const axis = { x1: x0, y1: top, x2: x0, y2: top + rowH * n };
    return { area, boxes, bars, axis, orientation: 'horizontal', labelAlign: 'right', captionLines: 2 };
  }

  const captionH = hasCaption ? 60 : 0;
  const labelH = 54;
  const valueH = 64;
  const baseline = area.y + area.h - (hasCaption ? captionH + 16 : 0) - labelH - 12;
  const maxBarH = baseline - (area.y + valueH + 8);
  const slotW = area.w / n;
  const barW = Math.min(180, slotW * 0.55);
  for (let i = 0; i < n; i++) {
    const cx = area.x + slotW * (i + 0.5);
    const h = Math.max(8, frac(values[i]) * maxBarH);
    const rect = { x: cx - barW / 2, y: baseline - h, w: barW, h };
    bars.push(rect);
    boxes[`bars.${i}.rect`] = rect;
    boxes[`bars.${i}.value`] = { x: cx - slotW * 0.45, y: baseline - h - 8 - valueH, w: slotW * 0.9, h: valueH };
    boxes[`bars.${i}.label`] = { x: cx - slotW * 0.45, y: baseline + 12, w: slotW * 0.9, h: labelH };
  }
  if (hasCaption) boxes.caption = { x: area.x, y: area.y + area.h - captionH, w: area.w, h: captionH };
  const axis = { x1: area.x, y1: baseline, x2: area.x + area.w, y2: baseline };
  return { area, boxes, bars, axis, orientation: 'vertical', labelAlign: 'center', captionLines: 1 };
}

// -------------------------------------------------------------- before/after

// Two panels (header, big icon, caption) with an arrow from "before" to "after".
// Side by side on landscape, top/bottom on portrait. `frames` are decorative panel outlines.
export function beforeAfterLayout(canvas = CANVAS) {
  const area = contentArea(canvas);
  const boxes = {};
  const frames = [];
  const headerH = 84;
  const captionH = 140;

  function panel(side, { x, y, w, h }, iconMax) {
    const iconSize = Math.min(iconMax, h - headerH - captionH - 60);
    const total = headerH + 20 + iconSize + 20 + captionH;
    const top = y + (h - total) / 2;
    const cx = x + w / 2;
    boxes[`${side}.header`] = boxAt(cx, top, w * 0.9, headerH);
    boxes[`${side}.icon`] = boxAt(cx, top + headerH + 20, iconSize, iconSize);
    boxes[`${side}.caption`] = boxAt(cx, top + headerH + 20 + iconSize + 20, w * 0.85, captionH);
    frames.push({ x: x + 8, y: top - 24, w: w - 16, h: total + 48 });
    return { iconCenterY: top + headerH + 20 + iconSize / 2, top, bottom: top + total };
  }

  if (isPortrait(canvas)) {
    const gap = 200;
    const panelH = (area.h - gap) / 2;
    const a = panel('before', { x: area.x, y: area.y, w: area.w, h: panelH }, 240);
    const b = panel('after', { x: area.x, y: area.y + panelH + gap, w: area.w, h: panelH }, 240);
    const cx = area.x + area.w / 2;
    const arrow = { x1: cx, y1: a.bottom + 40, x2: cx, y2: b.top - 40 };
    const mid = (arrow.y1 + arrow.y2) / 2;
    boxes.arrow_label = { x: cx + 30, y: mid - 25, w: area.w / 2 - 40, h: 50 };
    return { area, boxes, frames, arrow, arrowLabelAlign: 'left' };
  }

  const gap = 240;
  const panelW = (area.w - gap) / 2;
  const a = panel('before', { x: area.x, y: area.y, w: panelW, h: area.h }, 260);
  panel('after', { x: area.x + panelW + gap, y: area.y, w: panelW, h: area.h }, 260);
  const y = a.iconCenterY;
  const arrow = { x1: area.x + panelW + 30, y1: y, x2: area.x + panelW + gap - 30, y2: y };
  boxes.arrow_label = { x: arrow.x1, y: y - 80, w: arrow.x2 - arrow.x1, h: 50 };
  return { area, boxes, frames, arrow, arrowLabelAlign: 'center' };
}
