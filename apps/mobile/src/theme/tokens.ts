/** Side brand tokens for React Native (local until packages/design-tokens lands). */
export const palette = {
  indigo50: '#EEF0FF',
  indigo100: '#DDE1FF',
  indigo400: '#7C83FF',
  indigo500: '#5B5BF6',
  indigo600: '#4A44E0',
  indigo900: '#1B1840',
  ink950: '#0B0A16',
  ink900: '#13121F',
  ink850: '#1A1929',
  ink800: '#232236',
  ink700: '#33324A',
  ink500: '#6E6D85',
  ink400: '#9796AD',
  ink200: '#D9D8E5',
  ink100: '#ECEBF3',
  ink50: '#F6F6FA',
  white: '#FFFFFF',
  green500: '#16A34A',
  green400: '#34D399',
  red500: '#DC2626',
  red400: '#F87171',
  amber500: '#D97706',
  amber400: '#FBBF24',
  sky500: '#0284C7',
  sky400: '#38BDF8',
  slate500: '#64748B',
  slate400: '#94A3B8',
} as const;

export interface ThemeColors {
  background: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  accent: string;
  accentText: string;
  accentSoft: string;
  success: string;
  danger: string;
  warning: string;
  info: string;
  neutral: string;
  code: string;
  codeText: string;
  overlay: string;
}

export const lightColors: ThemeColors = {
  background: palette.ink50,
  surface: palette.white,
  surfaceAlt: palette.ink100,
  border: palette.ink200,
  text: palette.ink900,
  textMuted: palette.ink500,
  textSubtle: palette.ink400,
  accent: palette.indigo500,
  accentText: palette.white,
  accentSoft: palette.indigo50,
  success: palette.green500,
  danger: palette.red500,
  warning: palette.amber500,
  info: palette.sky500,
  neutral: palette.slate500,
  code: palette.indigo900,
  codeText: palette.indigo100,
  overlay: 'rgba(11,10,22,0.45)',
};

export const darkColors: ThemeColors = {
  background: palette.ink950,
  surface: palette.ink900,
  surfaceAlt: palette.ink850,
  border: palette.ink800,
  text: palette.ink50,
  textMuted: palette.ink400,
  textSubtle: palette.ink500,
  accent: palette.indigo400,
  accentText: palette.ink950,
  accentSoft: '#22204A',
  success: palette.green400,
  danger: palette.red400,
  warning: palette.amber400,
  info: palette.sky400,
  neutral: palette.slate400,
  code: '#0F0E1C',
  codeText: palette.indigo100,
  overlay: 'rgba(0,0,0,0.6)',
};

export const spacing = { xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 6, md: 10, lg: 16, pill: 999 } as const;
export const font = {
  caption: { fontSize: 12, lineHeight: 16 },
  body: { fontSize: 15, lineHeight: 21 },
  bodyStrong: { fontSize: 15, lineHeight: 21, fontWeight: '600' as const },
  title: { fontSize: 18, lineHeight: 24, fontWeight: '700' as const },
  largeTitle: { fontSize: 28, lineHeight: 34, fontWeight: '800' as const },
  mono: { fontSize: 13, lineHeight: 18, fontFamily: 'monospace' },
} as const;
