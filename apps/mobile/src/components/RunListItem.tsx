import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import type { Run } from '@/api/types';
import { agentLabel, duration, formatReward, relativeTime, shortTaskId } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';

import { StatusChip } from './StatusChip';
import { SText } from './ui';

export function RunListItem({ run, onPress }: { run: Run; onPress: () => void }) {
  const t = useTheme();
  const progress = run.max_steps ? Math.min(1, run.n_steps / run.max_steps) : 0;
  return (
    <Pressable
      testID={`run-item-${run.id}`}
      accessibilityRole="button"
      accessibilityLabel={`${shortTaskId(run.task_id)}, ${run.status}`}
      onPress={onPress}
      style={({ pressed }) => ({
        backgroundColor: pressed ? t.colors.surfaceAlt : t.colors.surface,
        borderRadius: t.radius.lg,
        borderWidth: 1,
        borderColor: t.colors.border,
        padding: t.spacing.lg,
        gap: t.spacing.sm,
      })}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm }}>
        <SText variant="bodyStrong" numberOfLines={1} style={{ flex: 1 }}>
          {shortTaskId(run.task_id)}
        </SText>
        <StatusChip status={run.status} size="sm" />
      </View>
      {run.goal ? (
        <SText color="muted" numberOfLines={2}>
          {run.goal}
        </SText>
      ) : null}
      {run.status === 'running' && run.max_steps ? (
        <View style={{ height: 4, borderRadius: 2, backgroundColor: t.colors.surfaceAlt, overflow: 'hidden' }}>
          <View style={{ width: `${Math.max(progress * 100, 4)}%`, height: 4, backgroundColor: t.colors.info }} />
        </View>
      ) : null}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, flexWrap: 'wrap' }}>
        <Meta icon="hardware-chip-outline" text={agentLabel(run.agent)} />
        <Meta icon="footsteps-outline" text={`${run.n_steps}${run.max_steps ? `/${run.max_steps}` : ''}`} />
        <Meta icon="trophy-outline" text={formatReward(run.reward)} />
        <Meta icon="time-outline" text={run.started_at ? duration(run.started_at, run.finished_at) : 'not started'} />
        <View style={{ flex: 1 }} />
        <SText variant="caption" color="subtle">
          {relativeTime(run.created_at)}
        </SText>
      </View>
    </Pressable>
  );
}

function Meta({ icon, text }: { icon: React.ComponentProps<typeof Ionicons>['name']; text: string }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <Ionicons name={icon} size={13} color={t.colors.textMuted} />
      <SText variant="caption" color="muted">
        {text}
      </SText>
    </View>
  );
}
