// Prints the WCAG AA contrast report for every theme and exits non-zero on failure.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { contrastRatio } from './lib/color.mjs';
import { evaluateContrast } from './lib/contrast-pairs.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const flat = JSON.parse(readFileSync(resolve(root, 'dist/json/tokens.flat.json'), 'utf8'));
const themes = {};
for (const [path, value] of Object.entries(flat)) {
  const m = path.match(/^theme\.(\w+)\.color\.(.+)$/);
  if (m) (themes[m[1]] ??= {})[m[2]] = value;
}
const results = evaluateContrast(themes, contrastRatio);
for (const r of results) {
  console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.theme.padEnd(5)}  ${r.ratio.toFixed(2).padStart(5)} >= ${r.min}  ${r.fg} on ${r.bg}  (${r.fgHex} / ${r.bgHex})`);
}
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} pairs meet WCAG AA`);
process.exit(failed.length ? 1 : 0);
