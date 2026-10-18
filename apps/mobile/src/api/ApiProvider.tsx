import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useSettings } from '@/settings/SettingsContext';

import { createHttpApi, type SideApi } from './client';
import { MockSideApi } from './mock/mockApi';

interface ApiContextValue {
  api: SideApi;
  /** Query-key scope so mock and real data never share cache entries. */
  scope: string;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, staleTime: 5_000 },
      mutations: { retry: 0 },
    },
  });
}

let sharedMock: MockSideApi | null = null;
function getSharedMock() {
  return (sharedMock ??= new MockSideApi());
}

export function ApiProvider({
  children,
  api: injected,
  queryClient: injectedClient,
}: {
  children: ReactNode;
  api?: SideApi;
  queryClient?: QueryClient;
}) {
  const { settings } = useSettings();
  const [queryClient] = useState(() => injectedClient ?? createQueryClient());
  const value = useMemo<ApiContextValue>(() => {
    if (injected) return { api: injected, scope: `injected:${injected.mode}` };
    if (settings.mockMode) return { api: getSharedMock(), scope: 'mock' };
    return { api: createHttpApi(settings.apiBaseUrl), scope: `http:${settings.apiBaseUrl}` };
  }, [injected, settings.mockMode, settings.apiBaseUrl]);

  useEffect(() => {
    queryClient.removeQueries({ predicate: (q) => q.queryKey[1] !== value.scope });
  }, [queryClient, value.scope]);

  return (
    <ApiContext.Provider value={value}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiContext.Provider>
  );
}

export function useApi(): ApiContextValue {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error('useApi must be used inside <ApiProvider>');
  return ctx;
}
