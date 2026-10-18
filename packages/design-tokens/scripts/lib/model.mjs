// Turns the resolved Style Dictionary token list into a small, platform-agnostic model
// that every output format (CSS, Tailwind, React Native, JSON, preview) renders from.

export const PALETTE_GROUPS = ['brand', 'accent', 'neutral', 'blue', 'green', 'red', 'amber'];
export const STATUSES = ['queued', 'running', 'succeeded', 'failed', 'cancelled'];

function setIn(obj, path, value) {
  let cur = obj;
  path.slice(0, -1).forEach((k) => (cur = cur[k] ??= {}));
  cur[path.at(-1)] = value;
}

const pick = (tokens, prefix) =>
  Object.fromEntries(
    tokens
      .filter((t) => t.path.length === prefix.length + 1 && prefix.every((p, i) => t.path[i] === p))
      .map((t) => [t.path.at(-1), t.value]),
  );

export function buildModel(allTokens) {
  const base = allTokens.filter((t) => t.path[0] !== 'theme');
  const themeTokens = allTokens.filter((t) => t.path[0] === 'theme');

  const palette = { white: pick(base, ['color']).white, black: pick(base, ['color']).black };
  for (const g of PALETTE_GROUPS) palette[g] = pick(base, ['color', g]);

  const themes = {};
  for (const t of themeTokens) {
    const [, mode, kind, ...rest] = t.path;
    themes[mode] ??= { colors: {}, colorsFlat: {}, shadows: {} };
    if (kind === 'color') {
      setIn(themes[mode].colors, rest, t.value);
      themes[mode].colorsFlat[rest.join('.')] = t.value;
    } else if (kind === 'shadow') {
      themes[mode].shadows[rest.join('.')] = t.value;
    }
  }

  const nestedBase = {};
  for (const t of base) setIn(nestedBase, t.path, t.value);

  return {
    tokens: allTokens,
    base,
    nestedBase,
    palette,
    themes,
    font: {
      family: pick(base, ['font', 'family']),
      nativeFamily: pick(base, ['font', 'family', 'native']),
      size: pick(base, ['font', 'size']),
      lineHeight: pick(base, ['font', 'lineHeight']),
      weight: pick(base, ['font', 'weight']),
      letterSpacing: pick(base, ['font', 'letterSpacing']),
    },
    typography: pick(base, ['typography']),
    space: pick(base, ['space']),
    radius: pick(base, ['radius']),
    borderWidth: pick(base, ['borderWidth']),
    duration: pick(base, ['motion', 'duration']),
    easing: pick(base, ['motion', 'easing']),
  };
}

export const kebab = (s) =>
  String(s)
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/\./g, '_')
    .toLowerCase();

export const cssVarName = (path) => `--side-${path.map(kebab).join('-')}`;
export const rem = (px) => (px === 0 ? '0' : `${+(px / 16).toFixed(4)}rem`);
export const px = (v) => (v === 0 ? '0' : `${v}px`);
export const bezier = (arr) => `cubic-bezier(${arr.join(', ')})`;
