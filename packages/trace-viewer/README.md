# @side/trace-viewer

React + TypeScript components for replaying BrowserGym episodes in Side (web and mobile web).
No app-framework dependency; peer deps are only `react`/`react-dom` >= 18. Ships ESM + `.d.ts` + one CSS file.

```tsx
import { RunReplayPlayer } from "@side/trace-viewer";
import "@side/trace-viewer/styles.css";

<RunReplayPlayer
  run={run}                       // Run
  steps={steps}                   // Step[] or StepDetail[] (GET /runs/{id}/steps)
  chat={chat}                     // ChatMessage[]
  apiBaseUrl="http://localhost:8000/api/v1"   // prefixes relative screenshot_url
  getStepDetail={(i) => fetch(`${api}/runs/${run.id}/steps/${i}`).then((r) => r.json())}
/>;
```

## Components

| Component | What it does |
|---|---|
| `RunReplayPlayer` | Composes everything: run header, screenshot + overlay, step card (action, thought, error), AXTree / Chat / Details tabs, play/pause, 0.5–4× speed, timeline. Keys: Space/`k` play, ←/→ (`j`/`l`) step. Follows new steps for live runs (`followLatest`). Stacks to one column under 760px. |
| `StepTimeline` | Scrubbable track (`role="slider"`): drag/click, ←/→/↑/↓, PageUp/PageDown (±`pageSize`), Home/End. Markers coloured by action category; failed actions red; terminal step square. |
| `ScreenshotViewer` | Zoom (−/+/Fit/1:1, Ctrl/⌘+wheel) and an optional bid overlay when `boxes` are given: `Target` (action bids), `SOM` (clickable / set-of-marks), `All`, `Off`. |
| `AXTreeViewer` | Collapsible tree parsed from `axtree_txt`; search by role/name/value/`[bid]` (Enter cycles matches); highlights + reveals the action's bid; marks `focused_element_bid`; arrow-key tree navigation. |
| `ActionBadge` | Parses action strings (`click('a42')`, `fill('b12', 'text')`, `drag_and_drop('1', '2')`, …) into name + bid chips + payload. |
| `ChatTranscript` | User / agent / info / infeasible messages; dims messages after the replay position (`until`). |

Parsers are exported too: `parseAction`, `parseActions` (multi-action), `tryParseAction`, `parseAXTree`, `boxesFromExtraProperties`.

## Semantics worth knowing

- **Action errors.** BrowserGym reports an action's error in the *next* observation's `last_action_error`. The player and timeline therefore attribute `steps[i+1].last_action_error` to step `i`'s action. If the runner stores the error on the step that issued the action, pass `errorAttribution="same"`.
- **Element boxes** are not in the contract yet; pass them via `getBoxes(index)` as `ElementBox[]` (`bbox = [x, y, w, h]` in screenshot pixels, i.e. BrowserGym `extra_element_properties[bid].bbox`). `boxesFromExtraProperties` converts BrowserGym's dict directly.
- **Theming.** All colours/fonts are `--stv-*` custom properties that default to `--side-*` tokens when present.

## Development

```bash
npm ci
npm run gen:types        # contracts/openapi.yaml -> src/generated/openapi.ts (openapi-typescript)
npm run check            # typecheck + vitest + tsup build + storybook build
npm run storybook        # http://localhost:6006
```

Fixtures in `fixtures/flight-search/` were recorded from a real BrowserGym episode
(`browsergym/openended` on `scripts/fixture_page.html`, scripted agent, incl. one failing action).
Regenerate with `python scripts/make_fixtures.py` (needs `browsergym-core` + Playwright Chromium).
`python scripts/screenshot_stories.py <out>` screenshots every story of a built Storybook.
