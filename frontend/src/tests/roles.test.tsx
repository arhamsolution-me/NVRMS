import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RolesPage } from '../pages/RolesPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockRoles = [
  { id: 'r-1', name: 'Super Admin', description: 'Root role', is_system: true },
  { id: 'r-2', name: 'Operator', description: 'Monitor live cams', is_system: false },
];

const mockPerms = [
  { permission_id: 'p-1', code: 'cameras:read', name: 'View Cameras', module: 'cameras', is_granted: true },
  { permission_id: 'p-2', code: 'cameras:write', name: 'Modify Cameras', module: 'cameras', is_granted: false },
];

describe('Roles and RBAC Permission Matrix', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't-1' } as any,
      permissions: new Set(['roles:read', 'roles:write', 'roles:manage_permissions']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders roles and fetches permissions matrix for selected role', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/roles') return mockRoles as any;
      if (url.includes('/permissions')) return mockPerms as any;
      return [] as any;
    });

    render(
      <ToastProvider>
        <RolesPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Super Admin')).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
    expect(await screen.findByText('View Cameras')).toBeInTheDocument();
    expect(screen.getByText('Modify Cameras')).toBeInTheDocument();
  });

  it('toggles permission and invokes PUT request with optimistic update', async () => {
    vi.spyOn(ClientModule.api, 'get').mockImplementation(async (url) => {
      if (url === '/roles') return mockRoles as any;
      if (url.includes('/permissions')) return mockPerms as any;
      return [] as any;
    });
    const putSpy = vi.spyOn(ClientModule.api, 'put').mockResolvedValue({ status: 'ok' } as any);

    render(
      <ToastProvider>
        <RolesPage />
      </ToastProvider>
    );

    expect(await screen.findByTestId('toggle-cameras:write')).toBeInTheDocument();

    const user = userEvent.setup();
    const toggleBtn = screen.getByTestId('toggle-cameras:write');
    await user.click(toggleBtn);

    expect(putSpy).toHaveBeenCalledWith('/roles/r-1/permissions', {
      permission_code: 'cameras:write',
      is_granted: true,
    });
  });
});
