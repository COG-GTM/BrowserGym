import { DarkTheme, DefaultTheme, Stack, ThemeProvider as NavThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useMemo } from 'react';
import { Platform } from 'react-native';

import { ApiProvider } from '@/api/ApiProvider';
import { loadNotifications } from '@/notifications/loader';
import { SettingsProvider, storedPushEnabled } from '@/settings/SettingsContext';
import { ThemeProvider, useTheme } from '@/theme/ThemeProvider';

if (Platform.OS !== 'web') {
  loadNotifications()?.setNotificationHandler({
    // The contract has no unregister endpoint, so pushes can still arrive after opting out; hide them locally.
    handleNotification: async () => {
      const show = await storedPushEnabled();
      return { shouldShowBanner: show, shouldShowList: show, shouldPlaySound: false, shouldSetBadge: false };
    },
  });
}

function ThemedStack() {
  const t = useTheme();
  const navTheme = useMemo(() => {
    const base = t.scheme === 'dark' ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: {
        ...base.colors,
        primary: t.colors.accent,
        background: t.colors.background,
        card: t.colors.surface,
        text: t.colors.text,
        border: t.colors.border,
      },
    };
  }, [t]);
  return (
    <NavThemeProvider value={navTheme}>
      <StatusBar style={t.scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: t.colors.surface },
          headerTintColor: t.colors.text,
          contentStyle: { backgroundColor: t.colors.background },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="runs/[id]" options={{ title: 'Run' }} />
      </Stack>
    </NavThemeProvider>
  );
}

export default function RootLayout() {
  return (
    <SettingsProvider>
      <ThemeProvider>
        <ApiProvider>
          <ThemedStack />
        </ApiProvider>
      </ThemeProvider>
    </SettingsProvider>
  );
}
