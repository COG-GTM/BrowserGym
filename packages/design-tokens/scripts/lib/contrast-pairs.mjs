// WCAG AA requirements for the semantic colour roles, checked for every theme.
// 4.5:1 = normal text (1.4.3), 3:1 = UI components & graphical objects (1.4.11).
export const TEXT = 4.5;
export const UI = 3;

const STATUSES = ['queued', 'running', 'succeeded', 'failed', 'cancelled'];
const SURFACES = ['bg.canvas', 'bg.surface', 'bg.subtle'];

export function contrastPairs() {
  const pairs = [];
  const add = (fg, bg, min, why) => pairs.push({ fg, bg, min, why });

  for (const bg of SURFACES) {
    add('fg.default', bg, TEXT, 'body text');
    add('fg.muted', bg, TEXT, 'secondary text');
    add('primary.fg', bg, TEXT, 'link / primary text');
    add('accent.fg', bg, TEXT, 'accent text');
    add('border.strong', bg, UI, 'input borders');
    add('border.focus', bg, UI, 'focus ring');
    add('primary.solid', bg, UI, 'primary button shape');
  }
  add('fg.inverse', 'bg.inverse', TEXT, 'inverse text (tooltips, toasts)');
  add('primary.fg', 'primary.subtle', TEXT, 'primary text on tinted bg');
  add('primary.onSolid', 'primary.solid', TEXT, 'primary button label');
  add('primary.onSolid', 'primary.solidHover', TEXT, 'primary button label (hover)');
  add('accent.fg', 'accent.subtle', TEXT, 'accent text on tinted bg');
  add('accent.onSolid', 'accent.solid', TEXT, 'accent button label');
  add('accent.onSolid', 'accent.solidHover', TEXT, 'accent button label (hover)');

  for (const s of STATUSES) {
    const k = `status.${s}`;
    add(`${k}.fg`, `${k}.subtle`, TEXT, `${s} badge text`);
    add(`${k}.onSolid`, `${k}.solid`, TEXT, `${s} solid badge text`);
    for (const bg of ['bg.canvas', 'bg.surface']) {
      add(`${k}.fg`, bg, TEXT, `${s} status text`);
      add(`${k}.solid`, bg, UI, `${s} status dot / icon`);
    }
  }
  return pairs;
}

export function evaluateContrast(themes, contrastRatio) {
  const results = [];
  for (const [theme, colors] of Object.entries(themes)) {
    for (const p of contrastPairs()) {
      const fg = colors[p.fg];
      const bg = colors[p.bg];
      if (!fg || !bg) throw new Error(`Missing colour role in ${theme}: ${!fg ? p.fg : p.bg}`);
      const ratio = contrastRatio(fg, bg);
      results.push({ theme, ...p, fgHex: fg, bgHex: bg, ratio, pass: ratio >= p.min });
    }
  }
  return results;
}
