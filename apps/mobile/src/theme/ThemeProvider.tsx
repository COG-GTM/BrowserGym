import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import type { RunStatus } from '@/api/types';
import { useSettings } from '@/settings/SettingsContext';

import { darkColors, font, lightColors, radius, spacing, type ThemeColors } from './tokens';

export interface Theme {
  scheme: 'light' | 'dark';
  colors: ThemeColors;
  spacing: typeof spacing;
  radius: typeof radius;
  font: typeof font;
}

export function buildTheme(scheme: 'light' | 'dark'): Theme {
  return { scheme, colors: scheme === 'dark' ? darkColors : lightColors, spacing, radius, font };
}

const ThemeContext = createContext<Theme>(buildTheme('light'));

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const { settings } = useSettings();
  const scheme = settings.appearance === 'system' ? (system === 'dark' ? 'dark' : 'light') : settings.appearance;
  const theme = useMemo(() => buildTheme(scheme), [scheme]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

export function statusColor(theme: Theme, status: RunStatus): string {
  switch (status) {
    case 'queued':
      return theme.colors.neutral;
    case 'running':
      return theme.colors.info;
    case 'succeeded':
      return theme.colors.success;
    case 'failed':
      return theme.colors.danger;
    case 'cancelled':
      return theme.colors.warning;
  }
}
