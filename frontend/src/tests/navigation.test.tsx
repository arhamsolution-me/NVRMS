import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Navbar } from '../components/layout/Navbar';
import { Sidebar } from '../components/layout/Sidebar';
import * as AuthContextModule from '../context/AuthContext';

describe('Navigation Shell (Navbar & Sidebar)', () => {
  it('Navbar renders tenant details, live indicator, and user info', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: 'u1',
        email: 'admin@nvrsms.local',
        name: 'Admin User',
        is_active: true,
        is_superuser: true,
        totp_enabled: true,
        tenant_id: 't1',
      },
      tenant: { id: 't1', name: 'Global Logistics Hub', slug: 'global' },
      permissions: new Set(),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    expect(screen.getByTestId('tenant-badge')).toHaveTextContent('Global Logistics Hub');
    expect(screen.getByTestId('ws-status-dot')).toHaveClass('connected');
    expect(screen.getByTestId('superuser-tag')).toBeInTheDocument();
    expect(screen.getByText('2FA')).toBeInTheDocument();
    expect(screen.getByText('AD')).toBeInTheDocument(); // Initials
  });

  it('Navbar toggles user menu and calls logout', async () => {
    const logoutMock = vi.fn();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: 'u1',
        email: 'operator@nvrsms.local',
        is_active: true,
        is_superuser: false,
        totp_enabled: false,
        tenant_id: 't1',
      },
      tenant: { id: 't1', name: 'Global Logistics Hub', slug: 'global' },
      permissions: new Set(),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: logoutMock,
      refreshProfile: vi.fn(),
      hasPermission: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    const user = userEvent.setup();
    const menuBtn = screen.getByTestId('user-profile-menu-button');
    await user.click(menuBtn);

    expect(screen.getByTestId('user-dropdown-menu')).toBeInTheDocument();
    const logoutBtn = screen.getByTestId('logout-button');
    await user.click(logoutBtn);

    expect(logoutMock).toHaveBeenCalledTimes(1);
  });

  it('Sidebar renders branding and all navigation links', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Sidebar />
      </MemoryRouter>
    );

    expect(screen.getByText('NVRSMS')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-dashboard')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-live-monitor')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-locations')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-nvrs---cameras')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-edge-agents')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-users---scopes')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-roles---rbac')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-audit-logs')).toBeInTheDocument();
    expect(screen.getByTestId('nav-link-system-settings')).toBeInTheDocument();
  });

  it('Sidebar toggles collapsed state', async () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );

    const sidebar = screen.getByTestId('app-sidebar');
    expect(sidebar).not.toHaveClass('sidebar-collapsed');

    const user = userEvent.setup();
    const toggleBtn = screen.getByTestId('sidebar-toggle-button');
    await user.click(toggleBtn);

    expect(sidebar).toHaveClass('sidebar-collapsed');
  });
});
