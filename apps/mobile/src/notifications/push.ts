import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

import type { SideApi } from '@/api/client';

import { loadNotifications } from './loader';

export type PushPlatform = 'ios' | 'android';

export interface PushRegistration {
  token: string;
  /** True when a placeholder token was used because a real Expo token is unavailable (simulator / Expo Go / mock). */
  simulated: boolean;
}

export class PushError extends Error {}

export function pushPlatform(): PushPlatform {
  return Platform.OS === 'ios' ? 'ios' : 'android';
}

async function getExpoToken(): Promise<string> {
  if (Platform.OS === 'web') throw new PushError('Push notifications are not supported on web.');
  if (!Device.isDevice) throw new PushError('Push notifications need a physical device.');
  const Notifications = loadNotifications();
  if (!Notifications) throw new PushError('Push notifications need a development build (unavailable in Expo Go).');
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('runs', {
      name: 'Run updates',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  const existing = await Notifications.getPermissionsAsync();
  const granted = existing.granted || (await Notifications.requestPermissionsAsync()).granted;
  if (!granted) throw new PushError('Notification permission was denied.');
  const projectId =
    process.env.EXPO_PUBLIC_EAS_PROJECT_ID ??
    Constants.expoConfig?.extra?.eas?.projectId ??
    Constants.easConfig?.projectId;
  if (!projectId) throw new PushError('No EAS projectId configured (set EXPO_PUBLIC_EAS_PROJECT_ID).');
  const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
  return data;
}

/**
 * Get an Expo push token and register it via POST /devices.
 * In mock mode a placeholder token is used when a real one cannot be obtained, so the flow stays demoable offline.
 */
export async function registerForPush(api: SideApi, runIds: string[] = []): Promise<PushRegistration> {
  let token: string;
  let simulated = false;
  try {
    token = await getExpoToken();
  } catch (error) {
    if (api.mode !== 'mock') throw error;
    token = `ExponentPushToken[mock-${Platform.OS}-${Date.now().toString(36)}]`;
    simulated = true;
  }
  await api.registerDevice({ expo_push_token: token, platform: pushPlatform(), run_ids: runIds });
  return { token, simulated };
}
