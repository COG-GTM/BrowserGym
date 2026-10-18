import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { contrastRatio } from '../scripts/lib/color.mjs';
import { contrastPairs, evaluateContrast } from '../scripts/lib/contrast-pairs.mjs';

const flat = JSON.parse(readFileSync(new URL('../dist/json/tokens.flat.json', import.meta.url), 'utf8'));
const themes = {};
for (const [path, value] of Object.entries(flat)) {
  const m = path.match(/^theme\.(\w+)\.color\.(.+)$/);
  if (m) (themes[m[1]] ??= {})[m[2]] = value;
}

test('contrast math matches WCAG reference values', () => {
  assert.equal(contrastRatio('#000000', '#FFFFFF'), 21);
  assert.equal(contrastRatio('#777777', '#777777'), 1);
  assert.equal(contrastRatio('#767676', '#FFFFFF').toFixed(2), '4.54');
});

test('light and dark themes are defined', () => {
  assert.deepEqual(Object.keys(themes).sort(), ['dark', 'light']);
});

for (const theme of ['light', 'dark']) {
  test(`${theme} theme meets WCAG AA for every semantic pair`, () => {
    const results = evaluateContrast({ [theme]: themes[theme] }, contrastRatio);
    assert.equal(results.length, contrastPairs().length);
    const failures = results.filter((r) => !r.pass).map((r) => `${r.fg} on ${r.bg}: ${r.ratio.toFixed(2)} < ${r.min}`);
    assert.deepEqual(failures, []);
  });
}
