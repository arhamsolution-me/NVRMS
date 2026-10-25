import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockAuditEvents = [
  {
    id: 'evt-1',
    action: 'STREAM_START',
    resource_type: 'stream',
    user_email: 'admin@nvrsms.local',
    timestamp: new Date().toISOString(),
  },
  {
    id: 'evt-2',
    action: 'LOGIN_SUCCESS',
    resource_type: 'auth',
    user_email: 'operator@nvrsms.local',
    timestamp: new Date().toISOString(),
  },
];

describe('Operational Telemetry Dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't-1', name: 'Global Logistics Hub' } as any,
      permissions: new Set(['audit:read']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders metric cards and live audit event stream', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/agents') return [{ id: 'a1', status: 'connected' }] as any;
      if (url === '/nvrs') return [{ id: 'n1', channel_count: 8 }] as any;
      if (url.includes('/audit')) return mockAuditEvents as any;
      return [] as any;
    });

    render(
      <MemoryRouter>
        <ToastProvider>
          <DashboardPage />
        </ToastProvider>
      </MemoryRouter>
    );

    expect(await screen.findByText('Operational Telemetry')).toBeInTheDocument();
    expect(screen.getByTestId('metric-active-streams')).toHaveTextContent('0');
    expect(screen.getByTestId('metric-online-agents')).toHaveTextContent('1 / 1');
    expect(screen.getByTestId('metric-health-status')).toHaveTextContent('100%');

    // Audit activity feed items
    expect(await screen.findByText('STREAM_START')).toBeInTheDocument();
    expect(screen.getByText('LOGIN_SUCCESS')).toBeInTheDocument();
  });

  it('triggers telemetry refresh on button click', async () => {
    const getSpy = vi.spyOn(ClientModule.api, 'get').mockResolvedValue([] as any);

    render(
      <MemoryRouter>
        <ToastProvider>
          <DashboardPage />
        </ToastProvider>
      </MemoryRouter>
    );

    const user = userEvent.setup();
    const refreshBtn = await screen.findByTestId('refresh-dashboard-btn');
    await user.click(refreshBtn);

    expect(getSpy).toHaveBeenCalled();
  });
});
