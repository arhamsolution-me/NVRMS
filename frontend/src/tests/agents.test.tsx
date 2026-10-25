import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentsPage } from '../pages/AgentsPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockAgents = [
  {
    id: 'agt-12345678-abcd',
    name: 'Toronto Edge Appliance',
    status: 'connected',
    version: '0.1.0',
    last_heartbeat: new Date().toISOString(),
  },
];

const mockDiag = {
  result: {
    timestamp: new Date().toISOString(),
    agent_version: '0.1.0',
    system: {
      os: 'Linux',
      release: '6.5.0',
      machine: 'x86_64',
      python_version: '3.11.9',
      cpu_count: 4,
    },
    disk: {
      total_bytes: 100000000000,
      used_bytes: 25000000000,
      free_bytes: 75000000000,
      percent_used: 25,
    },
    time_sync: {
      is_skewed: false,
      skew_seconds: 0.12,
    },
    active_streams: [],
    config: {
      hub_url: 'wss://hub.nvrsms.local/ws/agent',
      heartbeat_interval: 30,
      log_level: 'INFO',
    },
  },
};

describe('Edge Agent Fleet Management', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't-1' } as any,
      permissions: new Set(['agents:read', 'agents:enrol', 'agents:revoke']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders agent fleet table', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockAgents as any);

    render(
      <ToastProvider>
        <AgentsPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Toronto Edge Appliance')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('generates single-use enrolment code in modal', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockAgents as any);
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      code: 'ENROL-ABCD-1234',
      expires_at: new Date().toISOString(),
      name: 'New Branch Agent',
    } as any);

    render(
      <ToastProvider>
        <AgentsPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const enrolBtn = await screen.findByTestId('enrol-agent-btn');
    await user.click(enrolBtn);

    expect(screen.getByTestId('enrol-modal')).toBeInTheDocument();
    await user.type(screen.getByTestId('enrol-name-input'), 'New Branch Agent');

    await user.click(screen.getByTestId('generate-token-submit'));

    expect(postSpy).toHaveBeenCalledWith('/agents/enrol-token', {
      name: 'New Branch Agent',
    });

    expect(await screen.findByTestId('enrolment-code-display')).toHaveTextContent('ENROL-ABCD-1234');
  });

  it('opens diagnostics modal and displays sanitized hardware stats', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockAgents as any);
    vi.spyOn(ClientModule.api, 'post').mockResolvedValue(mockDiag as any);

    render(
      <ToastProvider>
        <AgentsPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const diagBtn = await screen.findByTestId('diag-btn-agt-12345678-abcd');
    await user.click(diagBtn);

    expect(screen.getByTestId('diagnostics-modal')).toBeInTheDocument();
    expect(await screen.findByTestId('diagnostics-content')).toBeInTheDocument();
    expect(screen.getByText(/Linux/i)).toBeInTheDocument();
    expect(screen.getByText(/25%/i)).toBeInTheDocument();
  });
});
