import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UsersPage } from '../pages/UsersPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockUsers = [
  {
    id: 'u-1',
    email: 'admin@nvrsms.local',
    full_name: 'System Super Admin',
    role_id: 'r-1',
    is_active: true,
    is_superuser: true,
    totp_enabled: true,
    scopes: [],
  },
  {
    id: 'u-2',
    email: 'operator@nvrsms.local',
    full_name: 'Branch Operator',
    role_id: 'r-2',
    is_active: false,
    is_superuser: false,
    totp_enabled: false,
    scopes: [{ id: 's-1', scope_type: 'site', scope_id: 'site-1' }],
  },
];

const mockRoles = [
  { id: 'r-1', name: 'Super Admin', is_system: true },
  { id: 'r-2', name: 'Site Operator', is_system: false },
];

describe('Users and Scopes Management', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't-1' } as any,
      permissions: new Set(['users:read', 'users:write']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders users table and role names', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/users') return mockUsers as any;
      if (url === '/roles') return mockRoles as any;
      return [] as any;
    });

    render(
      <ToastProvider>
        <UsersPage />
      </ToastProvider>
    );

    expect(await screen.findByText('System Super Admin')).toBeInTheDocument();
    expect(screen.getByText('admin@nvrsms.local')).toBeInTheDocument();
    expect(screen.getByText('Branch Operator')).toBeInTheDocument();
    expect(screen.getByText('operator@nvrsms.local')).toBeInTheDocument();
  });

  it('creates new user through modal', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/users') return mockUsers as any;
      if (url === '/roles') return mockRoles as any;
      return [] as any;
    });
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({ id: 'u-3' } as any);

    render(
      <ToastProvider>
        <UsersPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const createBtn = await screen.findByTestId('create-user-btn');
    await user.click(createBtn);

    expect(screen.getByTestId('user-modal')).toBeInTheDocument();
    await user.type(screen.getByTestId('user-fullname-input'), 'Auditor Alex');
    await user.type(screen.getByTestId('user-email-input'), 'auditor@nvrsms.local');
    await user.type(screen.getByTestId('user-password-input'), 'SecurePass123!');
    await user.selectOptions(screen.getByTestId('user-role-select'), 'r-2');

    await user.click(screen.getByTestId('user-modal-submit'));

    expect(postSpy).toHaveBeenCalledWith('/users', {
      email: 'auditor@nvrsms.local',
      full_name: 'Auditor Alex',
      password: 'SecurePass123!',
      role_id: 'r-2',
      is_active: true,
      scopes: [],
    });
  });
});
