// Visual constants shared by every scene. No React here so engine code can import it.

export const CANVAS = { width: 1920, height: 1080, fps: 30 };

export const SAFE_MARGIN = 96;

// Vertical (9:16) videos use the same theme on a 1080x1920 canvas.
export const CANVAS_PORTRAIT = { width: 1080, height: 1920, fps: 30 };

// Title band at the top of every non-title-card scene. Portrait titles may wrap to two lines.
export const TITLE_BAND = { height: 130, gapBelow: 34 };
export const TITLE_BAND_PORTRAIT = { height: 220, gapBelow: 40 };

export const COLORS = {
  ink: '#1f1f1f',
  paper: '#fbfaf7',
  grid: '#dde6ee',
  muted: '#6b6b6b',
  yellow: '#f5c518',
  red: '#e5533d',
  orange: '#f08c2e',
  green: '#7cc35a',
  blue: '#3b82c4',
};

// Only these names may appear in scene JSON (e.g. scale band colours).
export const PALETTE_NAMES = ['red', 'orange', 'yellow', 'green', 'blue'];

// Bar colours, in order (bar_chart).
export const BAR_COLORS = ['blue', 'orange', 'green', 'red', 'yellow'];

export const FONT_SIZES = {
  title: 92,
  heading: 120,
  subheading: 48,
  bigValue: 170,
  value: 72,
  label: 46,
  caption: 34,
  min: 22,
};

// On a vertical (9:16) video the same pixel size reads smaller (it is a phone screen held upright),
// so text caps are scaled up there. Boxes still bound the final size.
export const PORTRAIT_FONT_SCALE = 1.35;

export const STROKE = { ink: 5, arrow: 5 };

// Animation durations in seconds.
export const TIMING = {
  iconOutline: 0.5,
  iconFill: 0.3,
  textWipe: 0.45,
  shape: 0.4,
  stagger: 0.25,
};
