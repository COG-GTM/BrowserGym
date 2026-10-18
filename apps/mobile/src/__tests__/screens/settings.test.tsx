import { fireEvent, screen, userEvent, waitFor } from '@testing-library/react-native';

import SettingsScreen from '@/app/(tabs)/settings';
import { MockSideApi } from '@/api/mock/mockApi';
import { renderWithProviders } from '@/test/render';

describe('Settings screen', () => {
  it('registers for push via POST /devices (simulated token in mock mode)', async () => {
    const { api } = await renderWithProviders(<SettingsScreen />);
    fireEvent(screen.getByTestId('settings-push'), 'valueChange', true);
    await waitFor(() => expect((api as MockSideApi).registeredDevices).toHaveLength(1));
    expect((api as MockSideApi).registeredDevices[0].expo_push_token).toMatch(/^ExponentPushToken\[mock-/);
    expect(await screen.findByTestId('settings-push-status')).toHaveTextContent(/simulated token/);
  });

  it('tests the connection and edits the API URL', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<SettingsScreen />, {
      settings: { mockMode: false, apiBaseUrl: 'http://localhost:8000/api/v1' },
    });
    await user.press(screen.getByTestId('settings-test'));
    expect(await screen.findByTestId('settings-health')).toHaveTextContent(/Connected/);

    expect(screen.getByTestId('settings-save-url')).toBeDisabled();
    await user.clear(screen.getByTestId('settings-api-url'));
    await user.type(screen.getByTestId('settings-api-url'), 'http://10.0.0.5:8000/api/v1');
    expect(screen.getByTestId('settings-save-url')).toBeEnabled();
  });

  it('drops the push registration when the backend changes', async () => {
    await renderWithProviders(<SettingsScreen />, {
      settings: { mockMode: true, pushEnabled: true, pushToken: 'ExponentPushToken[mock-android-x]' },
    });
    expect(screen.getByTestId('settings-push')).toHaveProp('value', true);
    fireEvent(screen.getByTestId('settings-mock'), 'valueChange', false);
    await waitFor(() => expect(screen.getByTestId('settings-push')).toHaveProp('value', false));
    expect(screen.getByTestId('settings-push-status')).toHaveTextContent(/Backend changed/);
  });
});
