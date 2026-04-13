# Plan: Flow Visualization View Modes

## Context

The flows page renders protocol flows as animated step-by-step visualizations on a fixed topology diagram. Lines are drawn as straight SVG `<line>` elements that cut through unrelated NF boxes, all 25+ NFs are always visible, and past steps accumulate as overlapping green lines. This makes the diagram cluttered and hard to read, especially for complex flows like VoNR Call Setup (11 steps).

We're adding a **view mode toggle** with three modes so users can A/B test different visualizations:
1. **Topology** — current behavior (baseline)
2. **Sequence** — vertical sequence diagram (NFs as columns, arrows between them)
3. **Focused** — topology with curved lines, hidden uninvolved NFs, spotlight dimming

## Files to modify

1. **`gui/templates/flows.html`** — add toggle markup + CSS
2. **`gui/static/js/flow-viewer.js`** — add mode state, dispatchers, and two new renderers

No backend changes. No new files.

## API field names (verified)

Flow steps use: `from_component`, `to_component`, `via` (array), `step_order`, `protocol`, `interface`, `label`, `description`, `detail`, `failure_modes`, `metrics_to_watch`.

## Step 1: Toggle UI + scaffolding

**flows.html** — Insert view toggle in controls bar (line 100-101), between Next button and spacer:

```html
<div class="view-toggle">
  <button class="vt-btn active" data-mode="topology" onclick="setViewMode('topology')">Topology</button>
  <button class="vt-btn" data-mode="sequence" onclick="setViewMode('sequence')">Sequence</button>
  <button class="vt-btn" data-mode="focused" onclick="setViewMode('focused')">Focused</button>
</div>
```

Add CSS for `.view-toggle` and `.vt-btn` (follows existing `.inv-tab` pattern from investigate page). Add CSS for sequence diagram elements (`.seq-lifeline`, `.seq-arrow`) and focused mode (`.node-hidden`, `.node-dimmed`, `.node-spotlight`).

**flow-viewer.js** — Add:
- `let viewMode = 'topology'` state variable
- `setViewMode(mode)` — toggles active class, calls `renderForCurrentMode()`
- `renderForCurrentMode()` — dispatches to correct full renderer
- `highlightForCurrentMode()` — dispatches to correct highlight-only function
- Update `updateAll()` to call `highlightForCurrentMode()` instead of `highlightFlow()`
- Update `selectFlow()` to call `renderForCurrentMode()` instead of direct calls
- Update resize handler to call `renderForCurrentMode()`

## Step 2: Sequence diagram mode

New function `renderSequenceDiagram()` (~120 lines). Replaces SVG contents entirely.

**Column layout:**
- Extract unique participating NFs from all steps (ordered by first appearance)
- Space columns evenly across container width with margins
- Draw NF header boxes at top with layer-colored borders (reuse `LAYER_COLORS` from topology.js)
- Draw dashed vertical lifelines below each header

**Step arrows:**
- Each step = horizontal/diagonal arrow at a y-position (time flows down)
- Row spacing = `(availableHeight) / (totalSteps + 1)`, capped at 45px
- For steps with `via`: polyline through intermediate columns at same y
- Arrow markers via SVG `<defs>` (blue for current, green for past, dim for future)
- Label above each arrow: `protocol / interface` + step label
- Step number on the left margin

**Step highlighting:**
- Current step: `#58a6ff`, stroke-width 2.5
- Past steps: `#238636`, opacity 0.5
- Future steps: `#30363d`, opacity 0.2

**Dot animation:** Same D3 transition approach — waypoints are `[{x: fromColX, y}, ...viaColX, {x: toColX, y}]`. Calls `onDotArrived()` on completion for auto-play.

## Step 3: Focused topology mode

New function `highlightFlowFocused()` (~100 lines). Renders on top of `renderFlowTopology()`.

**Node management:**
- Collect all NFs participating in the current flow (across all steps)
- Hide non-participating NFs (opacity 0, pointer-events none)
- Hide all base topology edges (opacity 0)
- Current step's from/to/via NFs: full brightness
- Other participating NFs: dimmed (opacity 0.2)

**Curved flow lines:**
- New helper `curvedPath(fromPos, toPos, nodePositions)` — builds quadratic Bezier SVG path
- Detects if straight line passes through any NF box (point-to-segment distance < NODE_H + 10)
- If obstruction found: offset control point perpendicular to direct path (40px)
- If no obstruction: slight curve (10% of distance) for visual polish
- Helper `pointToSegmentDist(point, lineStart, lineEnd)` (~10 lines)

**Limited history:**
- Only draw current step (blue, width 3) and immediately previous step (green, width 2, opacity 0.4)
- NOT all past steps — this is the key clutter reduction

**Dot animation on curves:**
- Use SVG `path.getPointAtLength()` with D3 tween for smooth curve-following
- Multi-segment paths (via hops): concatenate into single `<path>`

## Step 4: Polish

- CSS transitions on node opacity changes (0.3s ease)
- Mode persists when switching flows or navigating steps
- Reset to no-step state (`currentStepIdx = -1`) works cleanly in all modes:
  - Topology: base topology, no lines
  - Sequence: headers + lifelines, no arrows
  - Focused: full topology visible, no lines

## Verification

1. Start the GUI: `cd gui && python server.py` (or however the dev server runs)
2. Navigate to http://localhost:8073/flows
3. Select "IMS Registration" flow — verify all 3 modes render correctly
4. Click through steps in each mode — verify dot animation and step highlighting
5. Use Play button — verify auto-advance works in all modes
6. Switch modes mid-flow — verify state preservation
7. Select "VoNR Call Setup" (11 steps, most complex flow) — verify sequence diagram scales
8. Resize browser window — verify responsive re-rendering
9. Select "Diameter Cx Authentication" (4 steps, simplest flow) — verify minimal flows render cleanly
