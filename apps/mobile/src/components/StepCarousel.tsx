import { Image } from 'expo-image';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, Pressable, View, useWindowDimensions, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';

import type { SideApi } from '@/api/client';
import type { Step } from '@/api/types';
import { formatReward } from '@/lib/format';
import { useTheme } from '@/theme/ThemeProvider';

import { Card, EmptyState, SText } from './ui';

interface Props {
  api: SideApi;
  runId: string;
  steps: Step[];
  live: boolean;
}

export function StepCarousel({ api, runId, steps, live }: Props) {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const itemWidth = Math.min(width, 720) - t.spacing.lg * 2;
  const gap = t.spacing.md;
  const listRef = useRef<FlatList<Step>>(null);
  const [selected, setIndex] = useState(0);
  const [follow, setFollow] = useState(true);
  const last = Math.max(0, steps.length - 1);
  const index = follow ? last : Math.min(selected, last);

  // While following, keep the newest step in view unless the user scrolled back.
  useEffect(() => {
    if (!follow || steps.length === 0) return;
    const frame = requestAnimationFrame(() => listRef.current?.scrollToIndex({ index: last, animated: true }));
    return () => cancelAnimationFrame(frame);
  }, [last, steps.length, follow]);

  const onMomentumEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const i = Math.round(e.nativeEvent.contentOffset.x / (itemWidth + gap));
      const clamped = Math.max(0, Math.min(steps.length - 1, i));
      setIndex(clamped);
      setFollow(clamped === steps.length - 1);
    },
    [itemWidth, gap, steps.length],
  );

  const goTo = (i: number) => {
    setIndex(i);
    setFollow(i === steps.length - 1);
    listRef.current?.scrollToIndex({ index: i, animated: true });
  };

  if (steps.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={live ? 'hourglass-outline' : 'albums-outline'}
          title={live ? 'Waiting for the first step…' : 'No steps recorded'}
          message={live ? 'Steps stream in here as the agent acts.' : undefined}
        />
      </Card>
    );
  }

  return (
    <View testID="step-carousel" style={{ gap: t.spacing.sm }}>
      <FlatList
        ref={listRef}
        data={steps}
        horizontal
        keyExtractor={(s) => String(s.index)}
        showsHorizontalScrollIndicator={false}
        snapToInterval={itemWidth + gap}
        decelerationRate="fast"
        disableIntervalMomentum
        onMomentumScrollEnd={onMomentumEnd}
        getItemLayout={(_, i) => ({ length: itemWidth + gap, offset: (itemWidth + gap) * i, index: i })}
        ItemSeparatorComponent={() => <View style={{ width: gap }} />}
        renderItem={({ item }) => <StepCard api={api} runId={runId} step={item} width={itemWidth} />}
        initialScrollIndex={Math.max(0, steps.length - 1)}
        onScrollToIndexFailed={() => undefined}
      />
      <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6 }}>
        {steps.map((s) => (
          <Pressable
            key={s.index}
            accessibilityRole="button"
            accessibilityLabel={`Go to step ${s.index}`}
            hitSlop={6}
            onPress={() => goTo(s.index)}
            style={{
              width: s.index === index ? 18 : 7,
              height: 7,
              borderRadius: 4,
              backgroundColor: s.index === index ? t.colors.accent : t.colors.border,
            }}
          />
        ))}
      </View>
      <SText variant="caption" color="subtle" style={{ textAlign: 'center' }} testID="step-position">
        {`Step ${index + 1} of ${steps.length}${live && follow ? ' · following live' : ''}`}
      </SText>
    </View>
  );
}

function StepCard({ api, runId, step, width }: { api: SideApi; runId: string; step: Step; width: number }) {
  const t = useTheme();
  const source = api.screenshotSource(runId, step);
  return (
    <Card style={{ width, padding: 0, overflow: 'hidden' }}>
      <View testID={`step-card-${step.index}`}>
        {source ? (
          <Image
            source={source}
            style={{ width: '100%', aspectRatio: 16 / 10, backgroundColor: t.colors.surfaceAlt }}
            contentFit="cover"
            transition={150}
            accessibilityLabel={`Screenshot for step ${step.index}`}
          />
        ) : (
          <View
            style={{
              width: '100%',
              aspectRatio: 16 / 10,
              backgroundColor: t.colors.surfaceAlt,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <SText color="subtle">No screenshot</SText>
          </View>
        )}
        <View style={{ padding: t.spacing.lg, gap: t.spacing.sm }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <SText variant="bodyStrong">{`Step ${step.index}`}</SText>
            <SText variant="caption" color="muted">
              {`reward ${formatReward(step.reward)}${step.elapsed_ms != null ? ` · ${Math.round(step.elapsed_ms)} ms` : ''}`}
            </SText>
          </View>
          <View style={{ backgroundColor: t.colors.code, borderRadius: t.radius.sm, padding: t.spacing.sm }}>
            <SText variant="mono" style={{ color: t.colors.codeText }} numberOfLines={3}>
              {step.action ?? '— reset —'}
            </SText>
          </View>
          {step.thought ? (
            <SText color="muted" numberOfLines={4}>
              {step.thought}
            </SText>
          ) : null}
          {step.last_action_error ? (
            <SText variant="caption" color="danger" numberOfLines={3}>
              {step.last_action_error}
            </SText>
          ) : null}
          {step.url ? (
            <SText variant="caption" color="subtle" numberOfLines={1}>
              {step.url}
            </SText>
          ) : null}
          {step.terminated || step.truncated ? (
            <SText variant="caption" color={step.terminated ? 'success' : 'danger'}>
              {step.terminated ? 'Episode terminated' : 'Episode truncated'}
            </SText>
          ) : null}
        </View>
      </View>
    </Card>
  );
}
