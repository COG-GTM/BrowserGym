import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { test } from 'node:test';

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');
const require = createRequire(import.meta.url);
const tokens = JSON.parse(read('dist/json/tokens.json'));
const statuses = read('../../contracts/openapi.yaml')
  .match(/RunStatus:\s*\{[^}]*enum:\s*\[([^\]]+)\]/)[1]
  .split(',')
  .map((s) => s.trim());

const cssBlock = (css, selector) => {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `missing ${selector}`);
  return css.slice(start, css.indexOf('}', start));
};
const varsIn = (block) => [...block.matchAll(/(--side-[\w-]+):/g)].map((m) => m[1]);

test('every RunStatus in the OpenAPI contract has status colours in both themes', () => {
  assert.deepEqual(statuses, ['queued', 'running', 'succeeded', 'failed', 'cancelled']);
  for (const theme of ['light', 'dark']) {
    for (const s of statuses) {
      assert.deepEqual(Object.keys(tokens.themes[theme].color.status[s]).sort(), ['border', 'fg', 'onSolid', 'solid', 'subtle']);
    }
  }
});

test('CSS: light and dark blocks define the same theme variables', () => {
  const css = read('dist/css/side.css');
  const dark = varsIn(cssBlock(css, '[data-theme="dark"]'));
  const light = varsIn(cssBlock(css, '[data-theme="light"]'));
  const media = varsIn(cssBlock(css, ':root:not([data-theme="light"])'));
  assert.ok(dark.length > 50);
  assert.deepEqual(dark, light);
  assert.deepEqual(media, dark);
  const root = varsIn(cssBlock(css, ':root'));
  for (const v of light) assert.ok(root.includes(v), `${v} missing from :root`);
  for (const v of ['--side-color-status-running-solid', '--side-color-bg-canvas-rgb', '--side-shadow-md', '--side-space-md', '--side-motion-easing-standard', '--side-font-size-md']) {
    assert.ok(root.includes(v), `${v} missing`);
  }
  assert.doesNotMatch(css, /undefined|NaN|\[object Object\]/);
});

test('Tailwind preset: CJS and ESM builds are identical and theme-aware', async () => {
  const cjs = require('../dist/tailwind/preset.cjs');
  const esm = (await import('../dist/tailwind/preset.mjs')).default;
  assert.deepEqual(cjs, esm);
  const { colors, fontSize, spacing, boxShadow } = cjs.theme.extend;
  assert.equal(colors.brand['500'], '#6461F2');
  assert.equal(colors.status.running.solid, 'rgb(var(--side-color-status-running-solid-rgb) / <alpha-value>)');
  assert.equal(colors.primary['on-solid'], 'rgb(var(--side-color-primary-on-solid-rgb) / <alpha-value>)');
  assert.equal(colors.accent['400'], '#36C7AE');
  assert.equal(colors.accent.solid, 'rgb(var(--side-color-accent-solid-rgb) / <alpha-value>)');
  assert.deepEqual(fontSize.md, ['1rem', { lineHeight: '1.5rem' }]);
  assert.equal(spacing.lg, '1.5rem');
  assert.equal(boxShadow.md, 'var(--side-shadow-md)');
  assert.equal(cjs.darkMode[0], 'variant');
  assert.match(cjs.darkMode[1].join('\n'), /prefers-color-scheme: dark[\s\S]*not\(\[data-theme="light"\]\)[\s\S]*\[data-theme="dark"\]/);
  const css = read('dist/css/side.css');
  for (const m of JSON.stringify(cjs).matchAll(/var\((--side-[\w-]+)\)/g)) assert.ok(css.includes(`${m[1]}:`), `${m[1]} not defined in side.css`);
});

test('Tailwind v4 theme.css only references defined variables', () => {
  const v4 = read('dist/tailwind/theme.css');
  const css = read('dist/css/side.css');
  assert.match(v4, /@theme inline/);
  assert.match(v4, /@custom-variant dark \{[\s\S]*\[data-theme="dark"\][\s\S]*prefers-color-scheme: dark[\s\S]*not\(\[data-theme="light"\]\)/);
  for (const m of v4.matchAll(/var\((--side-[\w-]+)\)/g)) assert.ok(css.includes(`${m[1]}:`), `${m[1]} not defined`);
});

test('React Native theme exports light + dark with numeric metrics', () => {
  const ts = read('dist/react-native/theme.ts');
  for (const name of ['lightTheme', 'darkTheme', 'themes', 'getTheme', 'statusColors', 'SideTheme']) assert.match(ts, new RegExp(`export (const|function|type) ${name}\\b`));
  assert.match(ts, /"fontWeight": "700"/);
  assert.match(ts, /"shadowOffset": \{/);
  assert.doesNotMatch(ts, /rem"|px"|undefined|NaN/);
});

test('JSON export contains base tokens, both themes and the contrast report', () => {
  assert.equal(tokens.base.color.brand['500'], '#6461F2');
  assert.equal(tokens.base.space.md, 16);
  assert.ok(tokens.contrast.length > 100);
  assert.ok(tokens.contrast.every((r) => r.pass));
});

test('preview page is generated and self-contained', () => {
  assert.ok(existsSync(new URL('../preview/index.html', import.meta.url)));
  const html = read('preview/index.html');
  assert.match(html, /--side-color-bg-canvas/);
  assert.match(html, /data-theme/);
  for (const s of statuses) assert.match(html, new RegExp(`Run #42 is ${s}`));
  assert.doesNotMatch(html, /<link |src="http|undefined|NaN|FAIL<\/td>/);
});
