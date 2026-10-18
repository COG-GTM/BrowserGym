// Type-level check that the generated theme drops into React Native style props.
import preset, { type SideTailwindPreset } from '../../dist/tailwind/preset';
import themes, { darkTheme, getTheme, lightTheme, statusColors, type RunStatus, type SideTheme } from '../../dist/react-native/theme';

type RNFontWeight = 'normal' | 'bold' | '100' | '200' | '300' | '400' | '500' | '600' | '700' | '800' | '900';
interface RNTextStyle {
  fontFamily?: string;
  fontSize?: number;
  lineHeight?: number;
  fontWeight?: RNFontWeight;
  letterSpacing?: number;
  color?: string;
}
interface RNViewStyle {
  backgroundColor?: string;
  borderRadius?: number;
  padding?: number;
  shadowColor?: string;
  shadowOffset?: { width: number; height: number };
  shadowOpacity?: number;
  shadowRadius?: number;
  elevation?: number;
}

const t: SideTheme = getTheme('dark');
const heading: RNTextStyle = { ...t.textStyles.h1, color: t.colors.fg.default };
const card: RNViewStyle = { backgroundColor: t.colors.bg.surface, borderRadius: t.radius.lg, padding: t.space.md, ...t.shadows.md };
const status: RunStatus = 'running';
const badge: RNViewStyle = { backgroundColor: statusColors(lightTheme, status).subtle };
const easing: readonly [number, number, number, number] = darkTheme.motion.easing.standard;
const p: SideTailwindPreset = preset;

export { badge, card, easing, heading, p, themes };
