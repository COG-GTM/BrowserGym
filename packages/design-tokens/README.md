# @side/design-tokens

Brand and design-system tokens for **Side** (the BrowserGym run launcher / live viewer / trace replayer), built with
[Style Dictionary](https://styledictionary.com) v4.

```
tokens/base/*.json      palette, typography, spacing, radii, border widths, motion
tokens/themes/*.json    semantic roles for light + dark (bg, fg, border, primary, accent, status.*, shadows)
scripts/build.mjs       Style Dictionary config + custom formats  ->  dist/ and preview/
dist/                   generated, committed so apps can consume it without a build step
preview/index.html      generated, self-contained swatch page (open it in a browser; ?theme=dark)
```

## Commands

```bash
npm install
npm run build      # regenerate dist/ + preview/
npm run contrast   # print the WCAG AA contrast report (non-zero exit on failure)
npm test           # build + node:test (contrast + output checks) + tsc typecheck
```

## Outputs

| Import | File | For |
|---|---|---|
| `@side/design-tokens/css` | `dist/css/side.css` | CSS custom properties (`--side-*`). Light on `:root`, dark via `prefers-color-scheme` or `[data-theme="dark"]`; `.side-text-*` type classes |
| `@side/design-tokens/tailwind` | `dist/tailwind/preset.{cjs,mjs,d.ts}` | Tailwind v3 preset (`presets: [require('@side/design-tokens/tailwind')]`) |
| `@side/design-tokens/tailwind/theme.css` | `dist/tailwind/theme.css` | Tailwind v4 `@theme` (import after `side.css`) |
| `@side/design-tokens/native` | `dist/react-native/theme.ts` | Expo / React Native: `lightTheme`, `darkTheme`, `getTheme(useColorScheme())`, `statusColors()` |
| `@side/design-tokens/json` | `dist/json/tokens.json` (+ `tokens.flat.json`) | Raw resolved values (px numbers, ms) + contrast report |

Semantic colours are theme-aware in CSS/Tailwind (they read `--side-color-*-rgb`, so opacity modifiers like
`bg-status-running-solid/40` work). Tailwind class names: `bg-bg-canvas`, `bg-bg-surface`, `text-fg-default`,
`text-fg-muted`, `border-border-default`, `bg-primary-solid text-primary-on-solid`, `bg-status-<status>-subtle
text-status-<status>-fg`, `bg-status-<status>-solid text-status-<status>-on-solid`, palette `bg-brand-500`, spacing
`p-md`, radius `rounded-lg`, `shadow-md`, `duration-fast ease-standard`.

Run status colours cover every `RunStatus` in `contracts/openapi.yaml`: `queued` (amber), `running` (blue),
`succeeded` (green), `failed` (red), `cancelled` (neutral). Each has `fg`, `subtle`, `border`, `solid`, `onSolid`.

### Consuming from the monorepo (no workspace manager)

```js
// apps/web/tailwind.config.js (Tailwind v3)
module.exports = { presets: [require('../../packages/design-tokens/dist/tailwind/preset.cjs')], content: [...] };
// apps/web/app/layout.tsx
import '../../../packages/design-tokens/dist/css/side.css';
```

```ts
// apps/mobile
import { getTheme } from '../../packages/design-tokens/dist/react-native/theme';
const theme = getTheme(useColorScheme());
```

## Accessibility

`scripts/lib/contrast-pairs.mjs` lists every semantic foreground/background pairing the UI uses; `npm test` fails
if any pair drops below WCAG 2.1 AA (4.5:1 text, 3:1 UI components / focus rings) in either theme.
`fg.disabled` is intentionally exempt (WCAG excludes inactive components).
