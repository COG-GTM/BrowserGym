import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, ScrollView, View } from 'react-native';

import { useRuns } from '@/api/hooks';
import { RUN_STATUSES, type RunStatus } from '@/api/types';
import { RunListItem } from '@/components/RunListItem';
import { Button, Chip, EmptyState, ErrorState } from '@/components/ui';
import { statusColor, useTheme } from '@/theme/ThemeProvider';

const LABELS: Record<RunStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export default function RunsScreen() {
  const t = useTheme();
  const [status, setStatus] = useState<RunStatus | undefined>();
  const query = useRuns(status);
  const runs = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await query.refetch();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ flexGrow: 0, flexShrink: 0 }}
        contentContainerStyle={{ paddingHorizontal: t.spacing.lg, paddingVertical: t.spacing.md, gap: t.spacing.sm }}
      >
        <Chip testID="filter-all" label="All" selected={!status} onPress={() => setStatus(undefined)} />
        {RUN_STATUSES.map((s) => (
          <Chip
            key={s}
            testID={`filter-${s}`}
            label={LABELS[s]}
            color={statusColor(t, s)}
            selected={status === s}
            onPress={() => setStatus(status === s ? undefined : s)}
          />
        ))}
      </ScrollView>
      {query.isError && runs.length === 0 ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <FlatList
          testID="runs-list"
          data={runs}
          keyExtractor={(r) => r.id}
          contentContainerStyle={{ padding: t.spacing.lg, paddingTop: 0, gap: t.spacing.md, flexGrow: 1 }}
          renderItem={({ item }) => (
            <RunListItem run={item} onPress={() => router.push({ pathname: '/runs/[id]', params: { id: item.id } })} />
          )}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={t.colors.accent} colors={[t.colors.accent]} />}
          onEndReached={() => query.hasNextPage && !query.isFetchingNextPage && query.fetchNextPage()}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={
            query.isPending ? (
              <ActivityIndicator style={{ marginTop: t.spacing.xxl }} color={t.colors.accent} />
            ) : (
              <EmptyState
                icon="rocket-outline"
                title={status ? `No ${LABELS[status].toLowerCase()} runs` : 'No runs yet'}
                message="Launch a BrowserGym episode and watch it here."
                action={<Button title="New run" icon="add" onPress={() => router.push('/new')} />}
              />
            )
          }
          ListFooterComponent={query.isFetchingNextPage ? <ActivityIndicator color={t.colors.accent} /> : undefined}
        />
      )}
    </View>
  );
}
