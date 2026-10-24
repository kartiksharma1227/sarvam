## title_card
Use for: the opening hook scene that names the topic. One heading, an optional subheading, one optional icon.
Slots:
- heading: the topic as a short title (max 40 characters)
- subheading: one line framing why it matters (max 60), or null
- icon_query: one icon, or null
- subheading_appear_on: a phrase from the narration when the subheading should appear, or null

## flow
Use for: a process or path where something moves from one thing to the next (A → B → C).
Slots:
- nodes: 2-4 steps, left to right. Each: label (max 14 characters), icon_query, appear_on
- arrow_labels: one short verb per arrow (exactly nodes-1 entries, max 12 characters each), or null

## comparison
Use for: two options side by side (before vs after, A vs B), compared on 1-3 measures.
Slots:
- left / right: column header (max 16 characters), icon_query, appear_on
- rows: 1-3 rows. Each row has a left and a right cell: value (max 10 characters, e.g. "9%"), caption (max 16), icon_query or null, appear_on (the words naming that value)

## stat
Use for: one striking number that anchors the lesson.
Slots:
- value: the number as shown on screen (max 8 characters, e.g. "720", "70%", "$1.2T")
- caption: what the number means (max 40)
- icon_query, appear_on (the words where the number is spoken)

## scale
Use for: a range split into named bands (ratings, levels, grades), optionally with a marker on one value.
Slots:
- stat: optional headline above the bands: value (max 12), caption (max 30), icon_query or null, appear_on or null
- bands: 2-5 bands in order. Each: label (max 12), range (max 12, e.g. "300-579"), color (red, orange, yellow, green or blue), appear_on
- marker_value: a number inside one band's range to point at, or null
- marker_appear_on: when the marker appears, or null

## checklist
Use for: a recap or a list of actions/tips.
Slots:
- items: 2-5 items. Each: text (max 24 characters), icon_query, appear_on

## cycle
Use for: a loop where the last step feeds back into the first.
Slots:
- nodes: 3-5 steps around the circle. Each: label (max 14 characters), icon_query, appear_on

## timeline
Use for: events in time order (history, stages over years).
Slots:
- events: 3-5 events. Each: date_label (max 10, e.g. "1971", "Year 5"), text (max 28), icon_query, appear_on

## venn
Use for: two things that differ but share something (two options with a common ground, two groups that overlap).
Slots:
- left / right: each circle's label (max 16 characters), icon_query, appear_on
- both: what they share, shown in the overlap: label (max 20 characters), appear_on (spoken after both sides)

## bar_chart
Use for: comparing real quantities side by side (shares, prices, counts over 2-6 categories). Use real, correct numbers. Every bar must measure the same kind of quantity in the same unit (e.g. caffeine per cup for each drink); never mix a limit, a total or a different unit into the chart. If the numbers have different units, use a different layout.
Slots:
- bars: 2-6 bars in the order they are spoken. Each: label (max 12 characters), value (the plain number the bar length is drawn from, e.g. 35), display (how it is written on screen, max 8 characters, e.g. "35%", "$1.2k"), appear_on
- caption: what the numbers measure (max 40 characters), or null

## before_after
Use for: a change or transformation (before vs after a habit, an invention, a treatment).
Slots:
- before / after: header (max 16 characters, e.g. "Before", "1990"), icon_query, caption (max 40 characters, the key fact), appear_on
- arrow_label: what caused the change (max 12 characters, e.g. "6 months"), or null

