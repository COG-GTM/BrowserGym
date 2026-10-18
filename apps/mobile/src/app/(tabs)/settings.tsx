import Constants from 'expo-constants';
import { useState } from 'react';
import { ScrollView, Switch, View } from 'react-native';

import { useApi } from '@/api/ApiProvider';
import { useHealth } from '@/api/hooks';
import { Button, Card, Chip, SText, SectionTitle, TextField } from '@/components/ui';
import { registerForPush } from '@/notifications/push';
import { defaultApiBaseUrl, useSettings, type Appearance } from '@/settings/SettingsContext';
import { useTheme } from '@/theme/ThemeProvider';

export default function SettingsScreen() {
  const t = useTheme();
  const { settings, update } = useSettings();
  const { api } = useApi();
  const [url, setUrl] = useState(settings.apiBaseUrl);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushStatus, setPushStatus] = useState<string | null>(null);
  const health = useHealth(false);

  const [savedUrl, setSavedUrl] = useState(settings.apiBaseUrl);
  if (savedUrl !== settings.apiBaseUrl) {
    setSavedUrl(settings.apiBaseUrl);
    setUrl(settings.apiBaseUrl);
  }
  const dirty = url.trim() !== settings.apiBaseUrl;

  const changeBackend = (patch: { mockMode?: boolean; apiBaseUrl?: string }) => {
    if (!settings.pushEnabled) return update(patch);
    update({ ...patch, pushEnabled: false, pushToken: null });
    setPushStatus('Backend changed: turn run notifications on again to register with it.');
  };

  const togglePush = async (enabled: boolean) => {
    if (!enabled) {
      update({ pushEnabled: false, pushToken: null });
      setPushStatus('Run notifications turned off on this device; incoming pushes are hidden.');
      return;
    }
    setPushBusy(true);
    setPushStatus(null);
    try {
      const reg = await registerForPush(api);
      update({ pushEnabled: true, pushToken: reg.token });
      setPushStatus(reg.simulated ? 'Registered with a simulated token (mock mode).' : 'Registered for run notifications.');
    } catch (error) {
      setPushStatus(error instanceof Error ? error.message : String(error));
      update({ pushEnabled: false, pushToken: null });
    } finally {
      setPushBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: t.spacing.lg, gap: t.spacing.lg }} keyboardShouldPersistTaps="handled">
      <View>
        <SectionTitle>Backend</SectionTitle>
        <Card style={{ gap: t.spacing.md }}>
          <Row label="Mock mode" hint="Use built-in fixtures and a simulated live run — no backend needed.">
            <Switch
              testID="settings-mock"
              value={settings.mockMode}
              onValueChange={(mockMode) => changeBackend({ mockMode })}
              trackColor={{ true: t.colors.accent, false: t.colors.border }}
            />
          </Row>
          <TextField
            testID="settings-api-url"
            label="API base URL"
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            editable={!settings.mockMode}
            hint={settings.mockMode ? 'Ignored while mock mode is on.' : `Default: ${defaultApiBaseUrl()}`}
          />
          <View style={{ flexDirection: 'row', gap: t.spacing.sm }}>
            <Button
              testID="settings-save-url"
              title="Save"
              variant="primary"
              disabled={!dirty || settings.mockMode}
              onPress={() => changeBackend({ apiBaseUrl: url.trim() })}
              style={{ flex: 1 }}
            />
            <Button
              testID="settings-test"
              title="Test connection"
              variant="secondary"
              icon="pulse"
              loading={health.isFetching}
              onPress={() => health.refetch()}
              style={{ flex: 1.4 }}
            />
          </View>
          {health.data ? (
            <SText color="success" testID="settings-health">{`Connected · ${health.data.status}${health.data.version ? ` · v${health.data.version}` : ''}`}</SText>
          ) : health.isError ? (
            <SText color="danger" testID="settings-health">{`Unreachable: ${(health.error as Error).message}`}</SText>
          ) : null}
        </Card>
      </View>

      <View>
        <SectionTitle>Notifications</SectionTitle>
        <Card style={{ gap: t.spacing.sm }}>
          <Row label="Run notifications" hint="Get a push when a run finishes (POST /devices with your Expo push token).">
            <Switch
              testID="settings-push"
              value={settings.pushEnabled}
              disabled={pushBusy}
              onValueChange={togglePush}
              trackColor={{ true: t.colors.accent, false: t.colors.border }}
            />
          </Row>
          {pushStatus ? <SText variant="caption" color="muted" testID="settings-push-status">{pushStatus}</SText> : null}
          {settings.pushToken ? (
            <SText variant="mono" color="subtle" numberOfLines={1}>
              {settings.pushToken}
            </SText>
          ) : null}
        </Card>
      </View>

      <View>
        <SectionTitle>Appearance</SectionTitle>
        <Card style={{ flexDirection: 'row', gap: t.spacing.sm }}>
          {(['system', 'light', 'dark'] as Appearance[]).map((a) => (
            <Chip
              key={a}
              testID={`appearance-${a}`}
              label={a[0].toUpperCase() + a.slice(1)}
              selected={settings.appearance === a}
              onPress={() => update({ appearance: a })}
            />
          ))}
        </Card>
      </View>

      <View>
        <SectionTitle>About</SectionTitle>
        <Card style={{ gap: 4 }}>
          <SText variant="bodyStrong">Side for BrowserGym</SText>
          <SText variant="caption" color="muted">
            {`App ${Constants.expoConfig?.version ?? '0.1.0'} · contract Side API 0.1.0 · ${api.mode} client`}
          </SText>
        </Card>
      </View>
    </ScrollView>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.spacing.md }}>
      <View style={{ flex: 1, gap: 2 }}>
        <SText variant="bodyStrong">{label}</SText>
        {hint ? (
          <SText variant="caption" color="muted">
            {hint}
          </SText>
        ) : null}
      </View>
      {children}
    </View>
  );
}
