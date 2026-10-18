import { Stack, useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useApi } from '@/api/ApiProvider';
import { useCancelRun, useChat, useRun, useRunEvents, useSendChat, useSteps } from '@/api/hooks';
import { isTerminal } from '@/api/types';
import { ChatBubble, ChatComposer } from '@/components/ChatPanel';
import { StatusChip } from '@/components/StatusChip';
import { StepCarousel } from '@/components/StepCarousel';
import { Button, Card, EmptyState, ErrorState, SText, SectionTitle } from '@/components/ui';
import { agentLabel, duration, formatReward, relativeTime, shortTaskId } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';

export default function RunDetailScreen() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useApi();
  const run = useRun(id);
  const steps = useSteps(id);
  const chat = useChat(id);
  const stream = useRunEvents(id, run.data?.status);
  const cancel = useCancelRun(id);
  const send = useSendChat(id);

  if (run.isPending) {
    return <ActivityIndicator style={{ marginTop: t.spacing.xxl }} color={t.colors.accent} />;
  }
  if (run.isError || !run.data) {
    return <ErrorState error={run.error ?? 'Run not found'} onRetry={() => run.refetch()} />;
  }

  const r = run.data;
  const active = !isTerminal(r.status);

  const confirmCancel = () => {
    if (Platform.OS === 'web') return cancel.mutate();
    Alert.alert('Cancel run?', 'The runner stops after the current step.', [
      { text: 'Keep running', style: 'cancel' },
      { text: 'Cancel run', style: 'destructive', onPress: () => cancel.mutate() },
    ]);
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      <Stack.Screen options={{ title: shortTaskId(r.task_id) }} />
      <ScrollView contentContainerStyle={{ padding: t.spacing.lg, gap: t.spacing.lg }} keyboardShouldPersistTaps="handled">
        <Card style={{ gap: t.spacing.md }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <StatusChip status={r.status} />
            <SText variant="caption" color={stream.state === 'live' ? 'success' : 'subtle'} testID="stream-state">
              {active ? (stream.state === 'live' ? '● Live' : stream.state === 'error' ? 'Reconnecting…' : 'Connecting…') : relativeTime(r.finished_at ?? r.created_at)}
            </SText>
          </View>
          {r.goal ? <SText testID="run-goal">{r.goal}</SText> : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: t.spacing.md }}>
            <Stat label="Steps" value={`${r.n_steps}${r.max_steps ? ` / ${r.max_steps}` : ''}`} testID="stat-steps" />
            <Stat label="Reward" value={formatReward(r.reward)} />
            <Stat label="Duration" value={duration(r.started_at, r.finished_at)} />
            <Stat label="Agent" value={agentLabel(r.agent)} />
          </View>
          {r.error ? (
            <SText color="danger" variant="caption">
              {r.error}
            </SText>
          ) : null}
          {active ? (
            <Button
              testID="run-cancel"
              title={r.status === 'queued' ? 'Cancel queued run' : 'Cancel run'}
              variant="danger"
              icon="stop-circle-outline"
              loading={cancel.isPending}
              onPress={confirmCancel}
            />
          ) : null}
        </Card>

        <View>
          <SectionTitle>Steps</SectionTitle>
          {steps.isPending ? (
            <ActivityIndicator color={t.colors.accent} />
          ) : (
            <StepCarousel api={api} runId={r.id} steps={steps.data ?? []} live={active} />
          )}
        </View>

        <View>
          <SectionTitle>Chat</SectionTitle>
          <Card style={{ gap: t.spacing.sm }}>
            {(chat.data ?? []).length === 0 ? (
              <EmptyState icon="chatbubbles-outline" title="No messages" message="Messages from the agent show up here." />
            ) : (
              chat.data!.map((m, i) => <ChatBubble key={`${m.timestamp}-${i}`} msg={m} />)
            )}
          </Card>
        </View>

        {stream.logs.length > 0 ? (
          <View>
            <SectionTitle>Runner log</SectionTitle>
            <Card style={{ gap: 2, backgroundColor: t.colors.code }}>
              {stream.logs.map((line, i) => (
                <SText key={i} variant="mono" style={{ color: t.colors.codeText }}>
                  {line}
                </SText>
              ))}
            </Card>
          </View>
        ) : null}
      </ScrollView>
      <View
        style={{
          paddingHorizontal: t.spacing.lg,
          paddingTop: t.spacing.sm,
          paddingBottom: Math.max(insets.bottom, t.spacing.sm),
          backgroundColor: t.colors.surface,
          borderTopWidth: 1,
          borderTopColor: t.colors.border,
        }}
      >
        <ChatComposer
          sending={send.isPending}
          placeholder={active ? 'Message the agent…' : 'Add a note to this run…'}
          onSend={(message) => send.mutateAsync(message)}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

function Stat({ label, value, testID }: { label: string; value: string; testID?: string }) {
  return (
    <View style={{ width: '50%', gap: 2 }}>
      <SText variant="caption" color="muted">
        {label}
      </SText>
      <SText variant="bodyStrong" numberOfLines={1} testID={testID}>
        {value}
      </SText>
    </View>
  );
}
