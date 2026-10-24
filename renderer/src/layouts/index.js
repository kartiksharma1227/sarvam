import { BarChart } from './BarChart.jsx';
import { BeforeAfter } from './BeforeAfter.jsx';
import { Checklist } from './Checklist.jsx';
import { Comparison } from './Comparison.jsx';
import { Cycle } from './Cycle.jsx';
import { Flow } from './Flow.jsx';
import { Scale } from './Scale.jsx';
import { Stat } from './Stat.jsx';
import { Timeline } from './Timeline.jsx';
import { TitleCard } from './TitleCard.jsx';
import { Venn } from './Venn.jsx';

// Layout name (scene.layout) -> component. Cue target names each layout reads are documented in its file;
// "title" always refers to the scene title.
export const LAYOUTS = {
  title_card: TitleCard,
  flow: Flow,
  comparison: Comparison,
  stat: Stat,
  scale: Scale,
  checklist: Checklist,
  cycle: Cycle,
  timeline: Timeline,
  venn: Venn,
  bar_chart: BarChart,
  before_after: BeforeAfter,
};
