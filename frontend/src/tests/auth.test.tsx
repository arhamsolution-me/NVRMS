import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../context/AuthContext';
import * as clientModule from '../api/client';

const AuthConsumer: React.FC = () => {
  const { user, isAuthenticated, hasPermission, login, logout, totpRequired } = useAuth();

  return (
    <div>
      <div data-testid="auth-status">{isAuthenticated ? 'authenticated' : 'unauthenticated'}</div>
      <div data-testid="totp-status">{totpRequired ? 'totp-required' : 'totp-not-required'}</div>
      <div data-testid="user-email">{user?.email || 'no-user'}</div>
      <div data-testid="can-view-cameras">{hasPermission('cameras:read') ? 'yes' : 'no'}</div>
      <div data-testid="can-delete-all">{hasPermission('system:nuke') ? 'yes' : 'no'}</div>
      <button
        data-testid="login-btn"
        onClick={() => login({ email: 'admin@nvrsms.local', password: 'SecretPassword123!' })}
      >
        Login
      </button>
      <button
        data-testid="login-totp-btn"
        onClick={() => login({ email: 'totp@nvrsms.local', password: 'SecretPassword123!' })}
      >
        Login TOTP
      </button>
      <button data-testid="logout-btn" onClick={() => logout()}>
        Logout
      </button>
    </div>
  );
};

describe('AuthContext and RBAC Enforcement', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('initializes with unauthenticated state', () => {
    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
    expect(screen.getByTestId('user-email')).toHaveTextContent('no-user');
    expect(screen.getByTestId('can-view-cameras')).toHaveTextContent('no');
  });

  it('handles successful login and populates profile and permissions', async () => {
    vi.spyOn(clientModule.api, 'post').mockImplementation(async (endpoint) => {
      if (endpoint === '/auth/login') {
        return { access_token: 'valid_mock_jwt_token', token_type: 'bearer', expires_in: 900 } as any;
      }
      return {} as any;
    });

    vi.spyOn(clientModule.api, 'get').mockImplementation(async (endpoint) => {
      if (endpoint === '/auth/me') {
        return {
          user: {
            id: 'u-1',
            email: 'admin@nvrsms.local',
            is_active: true,
            is_superuser: true,
            totp_enabled: false,
            tenant_id: 't-1',
          },
          tenant: { id: 't-1', name: 'HQ Corp', slug: 'hq' },
          permissions: ['cameras:read', 'cameras:write'],
        } as any;
      }
      return {} as any;
    });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId('login-btn'));

    expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');
    expect(screen.getByTestId('user-email')).toHaveTextContent('admin@nvrsms.local');
    // Superuser has all permissions
    expect(screen.getByTestId('can-view-cameras')).toHaveTextContent('yes');
    expect(screen.getByTestId('can-delete-all')).toHaveTextContent('yes');
  });

  it('handles TOTP requirement prompt when login signals totp_required', async () => {
    vi.spyOn(clientModule.api, 'post').mockResolvedValueOnce({
      totp_required: true,
      access_token: '',
      token_type: '',
      expires_in: 0,
    } as any);

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId('login-totp-btn'));

    expect(screen.getByTestId('totp-status')).toHaveTextContent('totp-required');
    expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
  });

  it('evaluates explicit permissions correctly for non-superusers', async () => {
    vi.spyOn(clientModule.api, 'post').mockResolvedValueOnce({
      access_token: 'operator_jwt_token',
      token_type: 'bearer',
      expires_in: 900,
    } as any);

    vi.spyOn(clientModule.api, 'get').mockResolvedValueOnce({
      user: {
        id: 'u-2',
        email: 'operator@nvrsms.local',
        is_active: true,
        is_superuser: false,
        totp_enabled: false,
        tenant_id: 't-1',
      },
      tenant: { id: 't-1', name: 'HQ Corp', slug: 'hq' },
      permissions: ['cameras:read'],
    } as any);

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId('login-btn'));

    expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');
    expect(screen.getByTestId('can-view-cameras')).toHaveTextContent('yes');
    expect(screen.getByTestId('can-delete-all')).toHaveTextContent('no');
  });

  it('resets state completely on logout', async () => {
    vi.spyOn(clientModule.api, 'post').mockResolvedValue({} as any);
    vi.spyOn(clientModule.api, 'get').mockResolvedValue({
      user: { id: 'u-1', email: 'admin@nvrsms.local', is_superuser: true },
      tenant: { id: 't-1' },
      permissions: [],
    } as any);

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId('login-btn'));
    expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');

    await user.click(screen.getByTestId('logout-btn'));
    expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
    expect(screen.getByTestId('user-email')).toHaveTextContent('no-user');
  });
});
