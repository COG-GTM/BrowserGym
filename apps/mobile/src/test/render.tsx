import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react-native';
import type { ReactElement } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiProvider } from '@/api/ApiProvider';
import type { SideApi } from '@/api/client';
import type { RunCreate } from '@/api/types';
import { MockSideApi } from '@/api/mock/mockApi';
import { SettingsProvider, type Settings } from '@/settings/SettingsContext';
import { ThemeProvider } from '@/theme/ThemeProvider';

const SAFE_AREA = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

/** A full RunCreate body (the generated type marks defaulted fields as required). */
export function runBody(task_id: string, extra: Partial<RunCreate> = {}): RunCreate {
  return {
    task_id,
    agent: { type: 'mock', model: null, use_screenshot: false, use_axtree: true },
    max_steps: 15,
    headless: true,
    ...extra,
  };
}

export function fastMockApi() {
  return new MockSideApi({ latencyMs: 0, startDelayMs: 0, stepIntervalMs: 15 });
}

export async function renderWithProviders(
  ui: ReactElement,
  { api = fastMockApi(), settings }: { api?: SideApi; settings?: Partial<Settings> } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
  const result = await render(
    <SafeAreaProvider initialMetrics={SAFE_AREA}>
      <SettingsProvider initial={{ mockMode: true, ...settings }}>
        <ThemeProvider>
          <ApiProvider api={api} queryClient={queryClient}>
            {ui}
          </ApiProvider>
        </ThemeProvider>
      </SettingsProvider>
    </SafeAreaProvider>,
  );
  return { ...result, api, queryClient };
}
