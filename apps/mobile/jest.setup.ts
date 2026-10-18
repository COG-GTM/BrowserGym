jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(() => Promise.resolve()),
  impactAsync: jest.fn(() => Promise.resolve()),
  notificationAsync: jest.fn(() => Promise.resolve()),
  NotificationFeedbackType: { Success: 'success', Warning: 'warning', Error: 'error' },
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
}));

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
  useLocalSearchParams: jest.fn(() => ({})),
  Stack: { Screen: () => null },
}));

jest.mock('@expo/vector-icons', () => {
  const { createElement } = require('react');
  const { Text } = require('react-native');
  const Ionicons = ({ name }: { name: string }) => createElement(Text, { accessibilityElementsHidden: true }, '');
  Ionicons.glyphMap = {};
  return { Ionicons };
});
