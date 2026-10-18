import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Switch, View } from 'react-native';

import { useAgents, useCreateRun, useTasks } from '@/api/hooks';
import type { AgentType } from '@/api/types';
import { Button, Card, Chip, SText, SectionTitle, TextField } from '@/components/ui';
import { useDebounced } from '@/lib/useDebounced';
import { useTheme } from '@/theme/ThemeProvider';

import { TaskRow } from './tasks';

export const OPENENDED = 'browsergym/openended';
const MAX_STEPS = 100;

export default function NewRunScreen() {
  const t = useTheme();
  const params = useLocalSearchParams<{ task?: string }>();
  const [taskId, setTaskId] = useState<string>(params.task ?? 'browsergym/miniwob.click-test');
  const [q, setQ] = useState('');
  const debounced = useDebounced(q, 250);
  const tasks = useTasks(debounced);
  const agents = useAgents();
  const [agentType, setAgentType] = useState<AgentType>('mock');
  const [modelChoice, setModel] = useState<string | null>(null);
  const [goal, setGoal] = useState('');
  const [startUrl, setStartUrl] = useState('https://example.com/');
  const [maxSteps, setMaxSteps] = useState(15);
  const [useScreenshot, setUseScreenshot] = useState(false);
  const create = useCreateRun();

  const [paramTask, setParamTask] = useState(params.task);
  if (params.task !== paramTask) {
    setParamTask(params.task);
    if (params.task) setTaskId(params.task);
  }

  const agent = agents.data?.find((a) => a.type === agentType);
  const models = useMemo(() => agent?.models ?? [], [agent]);
  const model = modelChoice && models.includes(modelChoice) ? modelChoice : (models[0] ?? null);

  const isOpenended = taskId === OPENENDED;
  const visibleTasks = (tasks.data ?? []).slice(0, q ? 8 : 5);
  const selectedTask = tasks.data?.find((task) => task.id === taskId);
  const goalMissing = isOpenended && goal.trim().length === 0;

  const submit = () => {
    if (goalMissing) return;
    create.mutate(
      {
        task_id: taskId,
        agent: { type: agentType, model, use_screenshot: useScreenshot, use_axtree: true },
        goal: isOpenended ? goal.trim() : null,
        start_url: isOpenended ? startUrl.trim() || null : null,
        max_steps: maxSteps,
        headless: true,
      },
      { onSuccess: (run) => router.push({ pathname: '/runs/[id]', params: { id: run.id } }) },
    );
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{ padding: t.spacing.lg, gap: t.spacing.lg }} keyboardShouldPersistTaps="handled">
        <View>
          <SectionTitle>Task</SectionTitle>
          <Card style={{ gap: t.spacing.sm }}>
            <TextField
              testID="new-task-search"
              value={q}
              onChangeText={setQ}
              placeholder="Search BrowserGym tasks"
              autoCapitalize="none"
              autoCorrect={false}
            />
            {visibleTasks.map((task) => (
              <TaskRow key={task.id} task={task} selected={task.id === taskId} onPress={() => setTaskId(task.id)} />
            ))}
            {selectedTask && !visibleTasks.some((task) => task.id === taskId) ? (
              <TaskRow task={selectedTask} selected onPress={() => undefined} />
            ) : null}
            {selectedTask?.requires_setup ? (
              <SText variant="caption" color="danger">
                This benchmark needs external servers / env vars on the runner.
              </SText>
            ) : null}
          </Card>
        </View>

        {isOpenended ? (
          <View>
            <SectionTitle>Goal</SectionTitle>
            <Card style={{ gap: t.spacing.md }}>
              <TextField
                testID="new-goal"
                label="Goal"
                value={goal}
                onChangeText={setGoal}
                placeholder="What should the agent do?"
                multiline
                hint={goalMissing ? 'Required for open-ended tasks.' : undefined}
              />
              <TextField
                testID="new-start-url"
                label="Start URL"
                value={startUrl}
                onChangeText={setStartUrl}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
              />
            </Card>
          </View>
        ) : null}

        <View>
          <SectionTitle>Agent</SectionTitle>
          <Card style={{ gap: t.spacing.md }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.sm }}>
              {(agents.data ?? []).map((a) => (
                <Chip
                  key={a.type}
                  testID={`agent-${a.type}`}
                  label={a.title}
                  selected={a.type === agentType}
                  onPress={() => setAgentType(a.type)}
                />
              ))}
            </View>
            {models.length > 0 ? (
              <View style={{ gap: t.spacing.xs }}>
                <SText variant="caption" color="muted" style={{ fontWeight: '600' }}>
                  MODEL
                </SText>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.sm }}>
                  {models.map((m) => (
                    <Chip key={m} label={m} selected={m === model} onPress={() => setModel(m)} />
                  ))}
                </View>
                <SText variant="caption" color="subtle">
                  {`Requires ${agentType === 'openai' ? 'OPENAI_API_KEY' : 'ANTHROPIC_API_KEY'} on the server.`}
                </SText>
              </View>
            ) : null}
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <SText>Use screenshots</SText>
              <Switch
                testID="new-use-screenshot"
                value={useScreenshot}
                onValueChange={setUseScreenshot}
                trackColor={{ true: t.colors.accent, false: t.colors.border }}
              />
            </View>
          </Card>
        </View>

        <View>
          <SectionTitle>Limits</SectionTitle>
          <Card style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <SText>Max steps</SText>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.spacing.md }}>
              <Stepper label="−" onPress={() => setMaxSteps((n) => Math.max(1, n - 1))} testID="max-steps-dec" />
              <SText variant="title" testID="max-steps-value" style={{ minWidth: 32, textAlign: 'center' }}>
                {String(maxSteps)}
              </SText>
              <Stepper label="+" onPress={() => setMaxSteps((n) => Math.min(MAX_STEPS, n + 1))} testID="max-steps-inc" />
            </View>
          </Card>
        </View>

        {create.isError ? (
          <SText color="danger" testID="new-error">
            {create.error instanceof Error ? create.error.message : 'Could not create run'}
          </SText>
        ) : null}
        <Button
          testID="new-submit"
          title="Launch run"
          icon="play"
          onPress={submit}
          loading={create.isPending}
          disabled={goalMissing}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Stepper({ label, onPress, testID }: { label: string; onPress: () => void; testID?: string }) {
  const t = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label === '+' ? 'Increase max steps' : 'Decrease max steps'}
      onPress={onPress}
      style={({ pressed }) => ({
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: pressed ? t.colors.border : t.colors.surfaceAlt,
      })}
    >
      <SText variant="title">{label}</SText>
    </Pressable>
  );
}
