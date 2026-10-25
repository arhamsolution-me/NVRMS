import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DevicesPage } from '../pages/DevicesPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockNvrs = [
  {
    id: 'nvr-1',
    name: 'Toronto HQ NVR',
    ip_address: '192.168.1.100',
    vendor: 'hikvision',
    web_port: 80,
    rtsp_port: 554,
    onvif_port: 8000,
    status: 'online',
    channel_count: 8,
    agent_id: 'agt-1',
    site_id: 'site-1',
  },
];

const mockCameras = [
  {
    id: 'cam-1',
    nvr_id: 'nvr-1',
    channel_number: 1,
    name: 'Main Lobby Entrance',
    is_ptz: false,
    status: 'online',
  },
  {
    id: 'cam-2',
    nvr_id: 'nvr-1',
    channel_number: 2,
    name: 'Parking Lot PTZ',
    is_ptz: true,
    status: 'online',
  },
];

describe('Devices (NVR and Camera) Management', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't-1' } as any,
      permissions: new Set(['nvrs:read', 'nvrs:write', 'nvrs:probe']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders NVRs list and fetches cameras on NVR selection', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/nvrs') return mockNvrs as any;
      if (url === '/agents') return [{ id: 'agt-1', name: 'Toronto Edge Box', status: 'connected' }] as any;
      if (url === '/locations/sites') return [{ id: 'site-1', name: 'Toronto HQ' }] as any;
      if (url.includes('/cameras')) return mockCameras as any;
      return [] as any;
    });

    render(
      <ToastProvider>
        <DevicesPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Toronto HQ NVR')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.100')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId('nvr-item-nvr-1'));

    expect(await screen.findByText('Main Lobby Entrance')).toBeInTheDocument();
    expect(screen.getByText('Parking Lot PTZ')).toBeInTheDocument();
  });

  it('probes NVR by IP via agent and displays discovered channels', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/nvrs') return mockNvrs as any;
      if (url === '/agents') return [{ id: 'agt-1', name: 'Toronto Edge Box', status: 'connected' }] as any;
      if (url === '/locations/sites') return [{ id: 'site-1', name: 'Toronto HQ' }] as any;
      return [] as any;
    });

    const probeSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      reachable: true,
      channels: [
        { channel: 1, name: 'Ch 1' },
        { channel: 2, name: 'Ch 2' },
      ],
    } as any);

    render(
      <ToastProvider>
        <DevicesPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const onboardBtn = await screen.findByTestId('onboard-nvr-btn');
    await user.click(onboardBtn);

    expect(screen.getByTestId('onboard-nvr-modal')).toBeInTheDocument();
    await user.type(screen.getByTestId('nvr-ip-input'), '192.168.1.200');

    const probeBtn = screen.getByTestId('probe-nvr-btn');
    await user.click(probeBtn);

    expect(probeSpy).toHaveBeenCalledWith('/nvrs/probe', expect.objectContaining({
      ip_address: '192.168.1.200',
      agent_id: 'agt-1',
    }));

    expect(await screen.findByTestId('probe-result-box')).toBeInTheDocument();
    expect(screen.getByText(/Probe Succeeded: 2 channels detected/i)).toBeInTheDocument();
  });
});
