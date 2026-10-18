import { View } from 'react-native';

import { useSettings } from '@/settings/SettingsContext';
import { useTheme } from '@/theme/ThemeProvider';

import { SText } from './ui';

export function MockBadge() {
  const t = useTheme();
  const { settings } = useSettings();
  if (!settings.mockMode) return null;
  return (
    <View
      testID="mock-badge"
      style={{
        marginHorizontal: t.spacing.lg,
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: t.radius.pill,
        backgroundColor: `${t.colors.warning}26`,
      }}
    >
      <SText variant="caption" style={{ color: t.colors.warning, fontWeight: '800', letterSpacing: 0.8 }}>
        MOCK
      </SText>
    </View>
  );
}
