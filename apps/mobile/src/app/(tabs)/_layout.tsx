import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import type { ColorValue } from 'react-native';

import { MockBadge } from '@/components/MockBadge';
import type { IconName } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';

function icon(name: IconName, focusedName: IconName) {
  function TabIcon({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) {
    return <Ionicons name={focused ? focusedName : name} color={color as string} size={size} />;
  }
  return TabIcon;
}

export default function TabsLayout() {
  const t = useTheme();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: t.colors.accent,
        tabBarInactiveTintColor: t.colors.textMuted,
        tabBarStyle: { backgroundColor: t.colors.surface, borderTopColor: t.colors.border },
        headerStyle: { backgroundColor: t.colors.surface },
        headerTitleStyle: { color: t.colors.text, fontWeight: '700' },
        headerShadowVisible: false,
        headerRight: () => <MockBadge />,
        sceneStyle: { backgroundColor: t.colors.background },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Runs', tabBarIcon: icon('pulse-outline', 'pulse') }} />
      <Tabs.Screen name="new" options={{ title: 'New Run', tabBarIcon: icon('add-circle-outline', 'add-circle') }} />
      <Tabs.Screen name="tasks" options={{ title: 'Tasks', tabBarIcon: icon('list-outline', 'list') }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings', tabBarIcon: icon('settings-outline', 'settings') }} />
    </Tabs>
  );
}
