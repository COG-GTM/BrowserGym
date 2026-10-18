import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';

export type Appearance = 'system' | 'light' | 'dark';

export interface Settings {
  apiBaseUrl: string;
  mockMode: boolean;
  appearance: Appearance;
  pushEnabled: boolean;
  pushToken: string | null;
}

export const SETTINGS_STORAGE_KEY = 'side.settings.v1';

export function defaultApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_SIDE_API_URL;
  if (fromEnv) return fromEnv;
  // The Android emulator reaches the host machine via 10.0.2.2.
  return Platform.OS === 'android' ? 'http://10.0.2.2:8000/api/v1' : 'http://localhost:8000/api/v1';
}

export function defaultSettings(): Settings {
  return {
    apiBaseUrl: defaultApiBaseUrl(),
    mockMode: process.env.EXPO_PUBLIC_SIDE_MOCK === '1',
    appearance: 'system',
    pushEnabled: false,
    pushToken: null,
  };
}

interface SettingsContextValue {
  settings: Settings;
  hydrated: boolean;
  update: (patch: Partial<Settings>) => void;
  reset: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children, initial }: { children: ReactNode; initial?: Partial<Settings> }) {
  const [settings, setSettings] = useState<Settings>(() => ({ ...defaultSettings(), ...initial }));
  const [hydrated, setHydrated] = useState(Boolean(initial));

  useEffect(() => {
    if (initial) return;
    let cancelled = false;
    AsyncStorage.getItem(SETTINGS_STORAGE_KEY)
      .then((raw) => {
        if (cancelled || !raw) return;
        const stored = JSON.parse(raw) as Partial<Settings>;
        setSettings((current) => ({ ...current, ...stored }));
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setHydrated(true));
    return () => {
      cancelled = true;
    };
  }, [initial]);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((current) => {
      const next = { ...current, ...patch };
      AsyncStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    const next = defaultSettings();
    setSettings(next);
    AsyncStorage.removeItem(SETTINGS_STORAGE_KEY).catch(() => undefined);
  }, []);

  const value = useMemo(() => ({ settings, hydrated, update, reset }), [settings, hydrated, update, reset]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used inside <SettingsProvider>');
  return ctx;
}
