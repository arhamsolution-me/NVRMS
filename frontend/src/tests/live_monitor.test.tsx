import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LiveMonitorPage } from '../pages/LiveMonitorPage';
import { ToastProvider } from '../context/ToastContext';
import * as ClientModule from '../api/client';

const mockCameras = [
  { id: 'c-1', name: 'Lobby Entrance', channel_number: 1, nvr_id: 'n-1', is_ptz: false, status: 'online' },
  { id: 'c-2', name: 'Server Room', channel_number: 2, nvr_id: 'n-1', is_ptz: false, status: 'online' },
  { id: 'c-3', name: 'Back Alley PTZ', channel_number: 3, nvr_id: 'n-1', is_ptz: true, status: 'online' },
];

describe('Multi-Camera Live Monitor Grid', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders 2x2 quad grid layout by default with 4 video cells', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockCameras as any);

    render(
      <ToastProvider>
        <LiveMonitorPage />
      </ToastProvider>
    );

    expect(await screen.findByTestId('video-cell-0')).toBeInTheDocument();
    expect(screen.getByTestId('video-cell-1')).toBeInTheDocument();
    expect(screen.getByTestId('video-cell-2')).toBeInTheDocument();
    expect(screen.getByTestId('video-cell-3')).toBeInTheDocument();
    expect(screen.queryByTestId('video-cell-4')).not.toBeInTheDocument();
  });

  it('switches between 1x1, 2x2, 3x3, and 4x4 grid modes', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockCameras as any);

    render(
      <ToastProvider>
        <LiveMonitorPage />
      </ToastProvider>
    );

    const user = userEvent.setup();

    // 1x1 mode
    await user.click(await screen.findByTestId('grid-1x1-btn'));
    expect(screen.getByTestId('video-cell-0')).toBeInTheDocument();
    expect(screen.queryByTestId('video-cell-1')).not.toBeInTheDocument();

    // 3x3 mode (9 cells)
    await user.click(screen.getByTestId('grid-3x3-btn'));
    expect(screen.getByTestId('video-cell-8')).toBeInTheDocument();
    expect(screen.queryByTestId('video-cell-9')).not.toBeInTheDocument();

    // 4x4 mode (16 cells)
    await user.click(screen.getByTestId('grid-4x4-btn'));
    expect(screen.getByTestId('video-cell-15')).toBeInTheDocument();
  });

  it('assigns camera from directory to selected cell slot', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockCameras as any);
    vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      token: 'mock_jwt_stream_token',
      stream_id: 's-1',
      stream_type: 'sub',
      viewer_id: 'v-1',
    } as any);

    render(
      <ToastProvider>
        <LiveMonitorPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Lobby Entrance')).toBeInTheDocument();

    const user = userEvent.setup();
    const camItem = screen.getByTestId('cam-item-c-1');
    await user.click(camItem);

    // Camera should now be assigned to Slot 0
    expect(await screen.findByTestId('canvas-stream-c-1')).toBeInTheDocument();
  });
});
