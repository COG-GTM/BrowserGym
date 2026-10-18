import { useEffect, useState } from 'react';
import { Animated, Text, View } from 'react-native';

import type { RunStatus } from '@/api/types';
import { statusColor, useTheme } from '@/theme/ThemeProvider';

const LABELS: Record<RunStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export function StatusChip({ status, size = 'md' }: { status: RunStatus; size?: 'sm' | 'md' }) {
  const t = useTheme();
  const color = statusColor(t, status);
  const [pulse] = useState(() => new Animated.Value(1));

  useEffect(() => {
    if (status !== 'running') return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.25, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [status, pulse]);

  return (
    <View
      testID={`status-${status}`}
      accessibilityLabel={`Status: ${LABELS[status]}`}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        alignSelf: 'flex-start',
        paddingHorizontal: size === 'sm' ? 8 : 10,
        paddingVertical: size === 'sm' ? 3 : 5,
        borderRadius: t.radius.pill,
        backgroundColor: `${color}22`,
      }}
    >
      <Animated.View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: color, opacity: pulse }} />
      <Text style={{ color, fontSize: size === 'sm' ? 11 : 12, fontWeight: '700' }}>{LABELS[status]}</Text>
    </View>
  );
}
