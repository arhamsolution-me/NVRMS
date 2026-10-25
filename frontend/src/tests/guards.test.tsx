import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from '../components/common/ProtectedRoute';
import { PermissionRoute } from '../components/common/PermissionRoute';
import * as AuthContextModule from '../context/AuthContext';

describe('Route Guards and Access Control', () => {
  it('ProtectedRoute redirects unauthenticated visitors to login', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      tenant: null,
      permissions: new Set(),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(false),
    });

    render(
      <MemoryRouter initialEntries={['/secret']}>
        <Routes>
          <Route path="/login" element={<div data-testid="login-view">Login Target</div>} />
          <Route
            path="/secret"
            element={
              <ProtectedRoute>
                <div data-testid="secret-view">Protected Content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('login-view')).toBeInTheDocument();
    expect(screen.queryByTestId('secret-view')).not.toBeInTheDocument();
  });

  it('ProtectedRoute allows authenticated visitors to view protected content', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: '1', email: 'admin@nvrsms.local', is_active: true, is_superuser: true, totp_enabled: false, tenant_id: 't1' },
      tenant: { id: 't1', name: 'HQ', slug: 'hq' },
      permissions: new Set(),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });

    render(
      <MemoryRouter initialEntries={['/secret']}>
        <Routes>
          <Route
            path="/secret"
            element={
              <ProtectedRoute>
                <div data-testid="secret-view">Protected Content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('secret-view')).toBeInTheDocument();
  });

  it('PermissionRoute displays 403 Access Denied when permission is revoked', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: '2', email: 'guard@nvrsms.local', is_active: true, is_superuser: false, totp_enabled: false, tenant_id: 't1' },
      tenant: { id: 't1', name: 'HQ', slug: 'hq' },
      permissions: new Set(['cameras:read']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockImplementation((p: string) => p === 'cameras:read'),
    });

    render(
      <MemoryRouter initialEntries={['/roles']}>
        <Routes>
          <Route
            path="/roles"
            element={
              <PermissionRoute permission="roles:write">
                <div data-testid="roles-admin-view">Admin Roles Matrix</div>
              </PermissionRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('access-denied-view')).toBeInTheDocument();
    expect(screen.getByText('roles:write')).toBeInTheDocument();
    expect(screen.queryByTestId('roles-admin-view')).not.toBeInTheDocument();
  });

  it('PermissionRoute renders children when permission is present', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: '2', email: 'guard@nvrsms.local', is_active: true, is_superuser: false, totp_enabled: false, tenant_id: 't1' },
      tenant: { id: 't1', name: 'HQ', slug: 'hq' },
      permissions: new Set(['cameras:read']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockImplementation((p: string) => p === 'cameras:read'),
    });

    render(
      <MemoryRouter initialEntries={['/cameras']}>
        <Routes>
          <Route
            path="/cameras"
            element={
              <PermissionRoute permission="cameras:read">
                <div data-testid="cameras-view">Camera Stream List</div>
              </PermissionRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('cameras-view')).toBeInTheDocument();
    expect(screen.queryByTestId('access-denied-view')).not.toBeInTheDocument();
  });
});
