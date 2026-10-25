import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditPage } from '../pages/AuditPage';
import { SettingsPage } from '../pages/SettingsPage';
import { ToastProvider } from '../context/ToastContext';
import * as ClientModule from '../api/client';

const mockLogs = [
  {
    id: 'log-1',
    tenant_id: 't-1',
    action: 'PERMISSION_TOGGLE',
    resource_type: 'role',
    resource_id: 'r-1',
    user_email: 'admin@nvrsms.local',
    ip_address: '10.0.0.15',
    timestamp: new Date().toISOString(),
    details: { permission: 'cameras:write', granted: true },
  },
  {
    id: 'log-2',
    tenant_id: 't-1',
    action: 'LOGIN_FAILED',
    resource_type: 'auth',
    user_email: 'hacker@nvrsms.local',
    ip_address: '185.220.101.5',
    timestamp: new Date().toISOString(),
    details: { reason: 'Invalid password' },
  },
];

describe('Audit Trail and Settings DR Engine', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('AuditPage displays audit rows and filters by action', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockLogs as any);

    render(
      <ToastProvider>
        <AuditPage />
      </ToastProvider>
    );

    expect(await screen.findByTestId('audit-row-log-1')).toBeInTheDocument();
    expect(screen.getByTestId('audit-row-log-2')).toBeInTheDocument();

    const user = userEvent.setup();
    const filterSelect = screen.getByTestId('audit-action-filter');
    await user.selectOptions(filterSelect, 'LOGIN_FAILED');

    expect(screen.queryByTestId('audit-row-log-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('audit-row-log-2')).toBeInTheDocument();
  });

  it('AuditPage opens details payload modal on click', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockLogs as any);

    render(
      <ToastProvider>
        <AuditPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const viewBtn = await screen.findByTestId('view-details-log-1');
    await user.click(viewBtn);

    expect(await screen.findByTestId('details-modal')).toBeInTheDocument();
    expect(screen.getByTestId('details-json-view')).toHaveTextContent('cameras:write');
  });

  it('SettingsPage executes encrypted backup and renders manifest stats', async () => {
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      archive_name: 'nvrsms_backup_test.enc',
      encrypted_size_bytes: 52400,
      raw_sha256: 'abc123rawhash',
      encrypted_sha256: 'def456enchash',
      timestamp: new Date().toISOString(),
    } as any);

    render(
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const backupBtn = screen.getByTestId('trigger-backup-btn');
    await user.click(backupBtn);

    expect(postSpy).toHaveBeenCalledWith('/backup/create', {});
    const pane = await screen.findByTestId('backup-result-pane');
    expect(within(pane).getByText(/nvrsms_backup_test.enc/i)).toBeInTheDocument();
  });

  it('SettingsPage executes scratch database restoration verification', async () => {
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({
      verified: true,
      status: 'PASSED',
      table_counts: { users: 3, cameras: 4 },
      rto_target_minutes: 15,
      rpo_target_hours: 1,
    } as any);

    render(
      <ToastProvider>
        <SettingsPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const verifyBtn = screen.getByTestId('verify-restore-btn');
    await user.click(verifyBtn);

    expect(postSpy).toHaveBeenCalledWith('/backup/verify', {});
    const pane = await screen.findByTestId('verify-result-pane');
    expect(within(pane).getByText(/Restore Verification PASSED/i)).toBeInTheDocument();
  });
});
