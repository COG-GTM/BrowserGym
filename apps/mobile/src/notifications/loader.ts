type NotificationsModule = typeof import('expo-notifications');

let cached: NotificationsModule | null | undefined;

/**
 * Lazily load expo-notifications. In Expo Go on Android (SDK 53+) importing it throws because
 * remote-push native modules are absent, so callers get `null` and degrade gracefully.
 */
export function loadNotifications(): NotificationsModule | null {
  if (cached !== undefined) return cached;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    cached = require('expo-notifications') as NotificationsModule;
  } catch {
    cached = null;
  }
  return cached;
}
