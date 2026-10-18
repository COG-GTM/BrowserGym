import { screen, userEvent, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import NewRunScreen from '@/app/(tabs)/new';
import { renderWithProviders } from '@/test/render';

describe('New Run screen', () => {
  beforeEach(() => jest.mocked(router.push).mockClear());

  it('launches a run with the chosen task, agent and max_steps', async () => {
    const user = userEvent.setup();
    const { api } = await renderWithProviders(<NewRunScreen />);
    const createRun = jest.spyOn(api, 'createRun');

    await user.press(await screen.findByTestId('task-browsergym/miniwob.login-user'));
    await user.press(await screen.findByTestId('agent-scripted'));
    await user.press(screen.getByTestId('max-steps-inc'));
    expect(screen.getByTestId('max-steps-value')).toHaveTextContent('16');
    await user.press(screen.getByTestId('new-submit'));

    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        task_id: 'browsergym/miniwob.login-user',
        agent: expect.objectContaining({ type: 'scripted' }),
        max_steps: 16,
        goal: null,
      }),
    );
  });

  it('requires a goal for the open-ended task and sends goal/start_url', async () => {
    const user = userEvent.setup();
    const { api } = await renderWithProviders(<NewRunScreen />);
    const createRun = jest.spyOn(api, 'createRun');

    await user.press(await screen.findByTestId('task-browsergym/openended'));
    expect(await screen.findByTestId('new-goal')).toBeOnTheScreen();
    expect(screen.getByTestId('new-submit')).toBeDisabled();

    await user.type(screen.getByTestId('new-goal'), 'Find the docs link');
    await user.clear(screen.getByTestId('new-start-url'));
    await user.type(screen.getByTestId('new-start-url'), 'https://example.org/');
    await user.press(screen.getByTestId('new-submit'));

    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(createRun.mock.calls[0][0]).toMatchObject({
      task_id: 'browsergym/openended',
      goal: 'Find the docs link',
      start_url: 'https://example.org/',
    });
  });

  it('filters tasks by search text', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<NewRunScreen />);
    await screen.findByTestId('task-browsergym/miniwob.click-test');
    await user.type(screen.getByTestId('new-task-search'), 'flight');
    expect(await screen.findByTestId('task-browsergym/miniwob.book-flight')).toBeOnTheScreen();
    await waitFor(() => expect(screen.queryByTestId('task-browsergym/miniwob.login-user')).not.toBeOnTheScreen());
  });

  it('keeps the selected task visible while search hides it', async () => {
    const user = userEvent.setup();
    await renderWithProviders(<NewRunScreen />);
    await user.press(await screen.findByTestId('task-browsergym/miniwob.login-user'));
    await user.type(screen.getByTestId('new-task-search'), 'flight');
    expect(await screen.findByTestId('task-browsergym/miniwob.book-flight')).toBeOnTheScreen();
    expect(screen.getByTestId('task-browsergym/miniwob.login-user')).toBeOnTheScreen();
  });
});
