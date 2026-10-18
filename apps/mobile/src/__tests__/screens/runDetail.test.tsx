import { screen, userEvent, waitFor } from '@testing-library/react-native';
import * as Haptics from 'expo-haptics';
import { useLocalSearchParams } from 'expo-router';
import { Alert } from 'react-native';

import RunDetailScreen from '@/app/runs/[id]';
import { fastMockApi, renderWithProviders, runBody } from '@/test/render';

describe('Run detail screen', () => {
  it('streams steps live, fires a haptic on completion and shows the replay', async () => {
    const api = fastMockApi();
    const run = await api.createRun(runBody('browsergym/miniwob.click-test'));
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: run.id });
    await renderWithProviders(<RunDetailScreen />, { api });

    expect(await screen.findByTestId('run-goal')).toHaveTextContent('Click the button labelled “Submit”.');
    expect(await screen.findByText('Succeeded', {}, { timeout: 3000 })).toBeOnTheScreen();
    expect(Haptics.notificationAsync).toHaveBeenCalledWith('success');
    expect(await screen.findByTestId('step-carousel')).toBeOnTheScreen();
    const total = (await api.listSteps(run.id)).length;
    expect(total).toBeGreaterThan(1);
    await waitFor(() => expect(screen.getByTestId('step-position')).toHaveTextContent(`Step ${total} of ${total}`));
    expect(screen.queryByTestId('run-cancel')).not.toBeOnTheScreen();
    api.dispose();
  });

  it('cancels a live run after confirmation', async () => {
    const api = fastMockApi();
    (api as unknown as { stepIntervalMs: number }).stepIntervalMs = 400;
    const run = await api.createRun(runBody('browsergym/miniwob.click-test'));
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: run.id });
    jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => {
      buttons?.find((b) => b.style === 'destructive')?.onPress?.();
    });
    const user = userEvent.setup();
    await renderWithProviders(<RunDetailScreen />, { api });

    await user.press(await screen.findByTestId('run-cancel'));
    expect(await screen.findByText('Cancelled', {}, { timeout: 3000 })).toBeOnTheScreen();
    expect((await api.getRun(run.id)).status).toBe('cancelled');
    api.dispose();
  });

  it('posts chat messages to /chat', async () => {
    const api = fastMockApi();
    (api as unknown as { stepIntervalMs: number }).stepIntervalMs = 400;
    const run = await api.createRun(runBody('browsergym/miniwob.click-test'));
    jest.mocked(useLocalSearchParams).mockReturnValue({ id: run.id });
    const sendChat = jest.spyOn(api, 'sendChat');
    const user = userEvent.setup();
    await renderWithProviders(<RunDetailScreen />, { api });

    await user.type(await screen.findByTestId('chat-input'), 'Use the email field too');
    await user.press(screen.getByTestId('chat-send'));
    await waitFor(() => expect(sendChat).toHaveBeenCalledWith(run.id, 'Use the email field too'));
    expect(await screen.findByText('Use the email field too')).toBeOnTheScreen();
    api.dispose();
  });
});
