import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LocationsPage } from '../pages/LocationsPage';
import { ToastProvider } from '../context/ToastContext';
import * as AuthContextModule from '../context/AuthContext';
import * as ClientModule from '../api/client';

const mockTree = [
  {
    id: 'prov-1',
    name: 'Ontario',
    code: 'ON',
    cities: [
      {
        id: 'city-1',
        name: 'Toronto',
        code: 'TOR',
        areas: [
          {
            id: 'area-1',
            name: 'Downtown Core',
            code: 'DT',
            sites: [
              {
                id: 'site-1',
                name: 'Financial Branch #101',
                code: 'FB101',
                address: '100 King St W',
              },
            ],
          },
        ],
      },
    ],
  },
];

describe('Locations Hierarchy Manager', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u1', email: 'admin@nvrsms.local', is_superuser: true } as any,
      tenant: { id: 't1', name: 'HQ' } as any,
      permissions: new Set(['locations:read', 'locations:write']),
      totpRequired: false,
      pendingEmail: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasPermission: vi.fn().mockReturnValue(true),
    });
  });

  it('renders location hierarchy tree correctly', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockTree as any);

    render(
      <ToastProvider>
        <LocationsPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Ontario')).toBeInTheDocument();
    expect(screen.getByText('Toronto')).toBeInTheDocument();
    expect(screen.getByText('Downtown Core')).toBeInTheDocument();
    expect(screen.getByText('Financial Branch #101')).toBeInTheDocument();
  });

  it('opens modal to create province and posts data', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockTree as any);
    const postSpy = vi.spyOn(ClientModule.api, 'post').mockResolvedValue({ id: 'p2', name: 'Quebec' } as any);

    render(
      <ToastProvider>
        <LocationsPage />
      </ToastProvider>
    );

    const user = userEvent.setup();
    const addBtn = await screen.findByTestId('add-province-btn');
    await user.click(addBtn);

    expect(screen.getByTestId('location-modal')).toBeInTheDocument();
    await user.type(screen.getByTestId('location-name-input'), 'Quebec');
    await user.type(screen.getByTestId('location-code-input'), 'QC');
    await user.click(screen.getByTestId('location-modal-submit'));

    expect(postSpy).toHaveBeenCalledWith('/locations/provinces', {
      name: 'Quebec',
      code: 'QC',
    });
  });

  it('filters sites based on search input', async () => {
    vi.spyOn(ClientModule.api, 'get').mockResolvedValue(mockTree as any);

    render(
      <ToastProvider>
        <LocationsPage />
      </ToastProvider>
    );

    expect(await screen.findByText('Financial Branch #101')).toBeInTheDocument();

    const user = userEvent.setup();
    const searchInput = screen.getByTestId('location-search-input');
    await user.type(searchInput, 'NonExistent');

    expect(screen.queryByText('Financial Branch #101')).not.toBeInTheDocument();
  });
});
