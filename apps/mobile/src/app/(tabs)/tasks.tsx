import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, ScrollView, View } from 'react-native';

import { useTasks } from '@/api/hooks';
import type { Task } from '@/api/types';
import { Chip, EmptyState, ErrorState, SText, TextField } from '@/components/ui';
import { useDebounced } from '@/lib/useDebounced';
import { shortTaskId } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';

export default function TasksScreen() {
  const t = useTheme();
  const [q, setQ] = useState('');
  const [benchmark, setBenchmark] = useState<string | undefined>();
  const debounced = useDebounced(q, 250);
  const all = useTasks('');
  const query = useTasks(debounced, benchmark);
  const benchmarks = useMemo(() => [...new Set((all.data ?? []).map((task) => task.benchmark))].sort(), [all.data]);

  return (
    <View style={{ flex: 1 }}>
      <View style={{ paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md }}>
        <TextField
          testID="tasks-search"
          value={q}
          onChangeText={setQ}
          placeholder="Search tasks (e.g. click, login)"
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
        />
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ flexGrow: 0, flexShrink: 0 }}
        contentContainerStyle={{ paddingHorizontal: t.spacing.lg, paddingVertical: t.spacing.md, gap: t.spacing.sm }}
      >
        <Chip label="All benchmarks" selected={!benchmark} onPress={() => setBenchmark(undefined)} />
        {benchmarks.map((b) => (
          <Chip key={b} label={b} selected={benchmark === b} onPress={() => setBenchmark(benchmark === b ? undefined : b)} />
        ))}
      </ScrollView>
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <FlatList
          testID="tasks-list"
          data={query.data ?? []}
          keyExtractor={(task) => task.id}
          contentContainerStyle={{ padding: t.spacing.lg, paddingTop: 0, gap: t.spacing.sm, flexGrow: 1 }}
          renderItem={({ item }) => (
            <TaskRow task={item} onPress={() => router.push({ pathname: '/new', params: { task: item.id } })} />
          )}
          ListEmptyComponent={
            query.isPending ? (
              <ActivityIndicator style={{ marginTop: t.spacing.xxl }} color={t.colors.accent} />
            ) : (
              <EmptyState icon="search-outline" title="No matching tasks" />
            )
          }
        />
      )}
    </View>
  );
}

export function TaskRow({ task, onPress, selected }: { task: Task; onPress: () => void; selected?: boolean }) {
  const t = useTheme();
  return (
    <Pressable
      testID={`task-${task.id}`}
      accessibilityRole="button"
      accessibilityState={{ selected: Boolean(selected) }}
      onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: t.spacing.md,
        padding: t.spacing.md,
        borderRadius: t.radius.md,
        borderWidth: 1,
        borderColor: selected ? t.colors.accent : t.colors.border,
        backgroundColor: selected ? t.colors.accentSoft : pressed ? t.colors.surfaceAlt : t.colors.surface,
      })}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm }}>
          <SText variant="bodyStrong" numberOfLines={1} style={{ flexShrink: 1 }}>
            {task.title}
          </SText>
          {task.requires_setup ? (
            <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: `${t.colors.warning}22` }}>
              <SText variant="caption" style={{ color: t.colors.warning, fontWeight: '700' }}>
                needs setup
              </SText>
            </View>
          ) : null}
        </View>
        <SText variant="caption" color="subtle" numberOfLines={1}>
          {shortTaskId(task.id)}
        </SText>
        {task.description ? (
          <SText variant="caption" color="muted" numberOfLines={2}>
            {task.description}
          </SText>
        ) : null}
      </View>
      <Ionicons
        name={selected ? 'checkmark-circle' : 'chevron-forward'}
        size={20}
        color={selected ? t.colors.accent : t.colors.textSubtle}
      />
    </Pressable>
  );
}
