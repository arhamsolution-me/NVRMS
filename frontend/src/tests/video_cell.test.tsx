import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { VideoCell, CameraDef } from '../components/streaming/VideoCell';
import { ToastProvider } from '../context/ToastContext';
import * as ClientModule from '../api/client';

const mockCamera: CameraDef = {
  id: 'cam-99',
  name: 'Vault High Security',
  channel_number: 1,
  is_ptz: true,
};

describe('VideoCell Streaming Player', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders empty slot state when no camera is assigned', () => {
    render(
      <ToastProvider>
        <VideoCell
          slotIndex={2}
          camera={null}
          onSelectSlot={vi.fn()}
          onRemoveCamera={vi.fn()}
          isSelected={false}
        />
      </ToastProvider>
    );

    expect(screen.getByTestId('empty-slot-2')).toBeInTheDocument();
    expect(screen.getByText(/Slot 3: Select Camera/i)).toBeInTheDocument();
  });

  it('requests stream token and toggles stream quality between sub and main', async () => {
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      token: 'jwt_sub_stream_token',
      stream_id: 's-99',
      stream_type: 'sub',
      viewer_id: 'viewer-abc',
    } as any);

    render(
      <ToastProvider>
        <VideoCell
          slotIndex={0}
          camera={mockCamera}
          onSelectSlot={vi.fn()}
          onRemoveCamera={vi.fn()}
          isSelected={true}
        />
      </ToastProvider>
    );

    expect(postSpy).toHaveBeenCalledWith('/streams/cam-99/token', {
      stream_type: 'sub',
    });

    expect(await screen.findByText('Vault High Security')).toBeInTheDocument();
    expect(screen.getByText('SUB')).toBeInTheDocument();

    const user = userEvent.setup();
    const qualityToggle = screen.getByTestId('quality-toggle-0');
    await user.click(qualityToggle);

    expect(postSpy).toHaveBeenCalledWith('/streams/cam-99/token', {
      stream_type: 'main',
    });
  });

  it('triggers snapshot action and displays toast', async () => {
    vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      token: 'jwt_sub_stream_token',
      stream_id: 's-99',
      stream_type: 'sub',
      viewer_id: 'viewer-abc',
    } as any);

    render(
      <ToastProvider>
        <VideoCell
          slotIndex={0}
          camera={mockCamera}
          onSelectSlot={vi.fn()}
          onRemoveCamera={vi.fn()}
          isSelected={false}
        />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const snapshotBtn = await screen.findByTestId('snapshot-btn-0');
    await user.click(snapshotBtn);

    expect(await screen.findByText(/Snapshot captured for Vault High Security/i)).toBeInTheDocument();
  });
});
