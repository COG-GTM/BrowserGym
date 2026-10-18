import { screen, userEvent, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import RunsScreen from '@/app/(tabs)/index';
import { LIVE_RUN_ID } from '@/api/mock/mockApi';
import { renderWithProviders } from '@/test/render';

describe('Runs screen', () => {
  it('lists runs with status chips, filters by status and opens a run', async () => {
    const user = userEvent.setup();
    const { api } = await renderWithProviders(<RunsScreen />);
    expect(await screen.findByTestId(`run-item-${LIVE_RUN_ID}`)).toBeOnTheScreen();
    expect(screen.getAllByText('Succeeded').length).toBeGreaterThan(1);

    await user.press(screen.getByTestId('filter-cancelled'));
    await waitFor(() => expect(screen.queryByTestId(`run-item-${LIVE_RUN_ID}`)).not.toBeOnTheScreen());
    const cancelled = (await api.listRuns({ status: 'cancelled' })).items;
    expect(await screen.findByTestId(`run-item-${cancelled[0].id}`)).toBeOnTheScreen();

    await user.press(screen.getByTestId(`run-item-${cancelled[0].id}`));
    expect(router.push).toHaveBeenCalledWith({ pathname: '/runs/[id]', params: { id: cancelled[0].id } });
  });
});
