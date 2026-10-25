import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import {
  Users,
  Plus,
  ShieldCheck,
  Shield,
  Trash2,
  Edit2,
  Search,
  CheckCircle,
  XCircle,
  MapPin,
} from 'lucide-react';

interface ScopeItem {
  id?: string;
  scope_type: string;
  scope_id: string;
}

interface UserItem {
  id: string;
  email: string;
  full_name: string;
  role_id: string;
  is_active: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  scopes?: ScopeItem[];
}

interface RoleItem {
  id: string;
  name: string;
  is_system: boolean;
}

export const UsersPage: React.FC = () => {
  const { user: currentUser, hasPermission } = useAuth();
  const { showToast } = useToast();

  const [users, setUsers] = useState<UserItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    email: '',
    full_name: '',
    password: '',
    role_id: '',
    is_active: true,
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [usersData, rolesData] = await Promise.all([
        api.get<UserItem[]>('/users'),
        api.get<RoleItem[]>('/roles'),
      ]);
      setUsers(usersData);
      setRoles(rolesData);
    } catch {
      showToast('Failed to load user and role data', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleOpenCreate = () => {
    setEditingUserId(null);
    setFormData({
      email: '',
      full_name: '',
      password: '',
      role_id: roles[0]?.id || '',
      is_active: true,
    });
    setIsModalOpen(true);
  };

  const handleOpenEdit = (user: UserItem) => {
    setEditingUserId(user.id);
    setFormData({
      email: user.email,
      full_name: user.full_name,
      password: '',
      role_id: user.role_id,
      is_active: user.is_active,
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingUserId) {
        // Update user
        const updatePayload: Record<string, unknown> = {
          full_name: formData.full_name,
          role_id: formData.role_id,
          is_active: formData.is_active,
        };
        if (formData.password) {
          updatePayload.password = formData.password;
        }
        await api.patch(`/users/${editingUserId}`, updatePayload);
        showToast('User profile updated successfully', 'success');
      } else {
        // Create user
        await api.post('/users', {
          email: formData.email,
          full_name: formData.full_name,
          password: formData.password,
          role_id: formData.role_id,
          is_active: formData.is_active,
          scopes: [],
        });
        showToast('New user created successfully', 'success');
      }
      setIsModalOpen(false);
      await fetchData();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to save user', 'error');
    }
  };

  const handleDelete = async (user: UserItem) => {
    if (user.id === currentUser?.id) {
      showToast('You cannot delete your own active session account', 'warning');
      return;
    }
    if (!window.confirm(`Are you sure you want to delete user "${user.email}"?`)) {
      return;
    }

    try {
      await api.delete(`/users/${user.id}`);
      showToast(`User ${user.email} removed`, 'success');
      await fetchData();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to delete user', 'error');
    }
  };

  const filteredUsers = users.filter((u) => {
    const q = searchQuery.toLowerCase();
    return u.email.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q);
  });

  const getRoleName = (roleId: string) => {
    const r = roles.find((role) => role.id === roleId);
    return r ? r.name : 'Unknown Role';
  };

  return (
    <div data-testid="users-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Users & Scopes</h1>
          <p className="page-description">
            Account provisioning, role mapping, and hierarchical location scoping
          </p>
        </div>
        {hasPermission('users:write') && (
          <button onClick={handleOpenCreate} className="btn btn-primary" data-testid="create-user-btn">
            <Plus size={16} /> New User Account
          </button>
        )}
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ padding: '16px', marginBottom: '20px' }}>
        <div style={{ position: 'relative', maxWidth: '360px' }}>
          <Search
            size={16}
            color="var(--text-muted)"
            style={{ position: 'absolute', left: '12px', top: '10px' }}
          />
          <input
            type="text"
            placeholder="Search by name or email..."
            className="form-input"
            style={{ paddingLeft: '36px' }}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            data-testid="users-search-input"
          />
        </div>
      </div>

      {/* Users Table */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>USER</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>ROLE</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>STATUS</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>2FA</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>SCOPES</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>
                ACTIONS
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  Loading user directory...
                </td>
              </tr>
            ) : filteredUsers.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  <Users size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                  <p>No user accounts found.</p>
                </td>
              </tr>
            ) : (
              filteredUsers.map((user) => (
                <tr
                  key={user.id}
                  style={{ borderBottom: '1px solid var(--border-subtle)' }}
                  data-testid={`user-row-${user.id}`}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{user.full_name}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{user.email}</div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Shield size={14} color="var(--color-primary)" />
                      <span style={{ fontWeight: 500 }}>{getRoleName(user.role_id)}</span>
                      {user.is_superuser && (
                        <span className="badge badge-info" style={{ fontSize: '10px' }}>
                          Root
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    {user.is_active ? (
                      <span className="badge badge-online">
                        <CheckCircle size={12} /> Active
                      </span>
                    ) : (
                      <span className="badge badge-offline">
                        <XCircle size={12} /> Inactive
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    {user.totp_enabled ? (
                      <span className="badge badge-online" title="TOTP 2FA Protected">
                        <ShieldCheck size={12} /> Enabled
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Disabled</span>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <MapPin size={14} color="var(--text-muted)" />
                      <span>
                        {user.scopes && user.scopes.length > 0
                          ? `${user.scopes.length} Scoped Area(s)`
                          : user.is_superuser
                            ? 'Global (Unrestricted)'
                            : 'Default Tenant'}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    {hasPermission('users:write') && (
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => handleOpenEdit(user)}
                          className="btn btn-secondary"
                          style={{ padding: '4px 8px', fontSize: '12px' }}
                          title="Edit User"
                          data-testid={`edit-user-btn-${user.id}`}
                        >
                          <Edit2 size={13} />
                        </button>
                        <button
                          onClick={() => handleDelete(user)}
                          className="btn"
                          style={{
                            padding: '4px 8px',
                            fontSize: '12px',
                            color: 'var(--status-offline)',
                            backgroundColor: 'var(--status-offline-bg)',
                          }}
                          title="Delete User"
                          data-testid={`delete-user-btn-${user.id}`}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* User Create / Edit Modal */}
      {isModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
          }}
          data-testid="user-modal"
        >
          <div className="card" style={{ width: '440px', padding: '24px', backgroundColor: '#ffffff' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
              {editingUserId ? 'Edit User Account' : 'Provision User Account'}
            </h3>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="user-fullname">
                  Full Name
                </label>
                <input
                  id="user-fullname"
                  type="text"
                  required
                  className="form-input"
                  placeholder="e.g. Alex Johnson"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  data-testid="user-fullname-input"
                />
              </div>

              {!editingUserId && (
                <div className="form-group">
                  <label className="form-label" htmlFor="user-email">
                    Email Address
                  </label>
                  <input
                    id="user-email"
                    type="email"
                    required
                    className="form-input"
                    placeholder="user@organization.local"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    data-testid="user-email-input"
                  />
                </div>
              )}

              <div className="form-group">
                <label className="form-label" htmlFor="user-password">
                  {editingUserId ? 'New Password (leave blank to retain)' : 'Password'}
                </label>
                <input
                  id="user-password"
                  type="password"
                  required={!editingUserId}
                  minLength={8}
                  className="form-input"
                  placeholder="••••••••••••"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  data-testid="user-password-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="user-role">
                  Assigned RBAC Role
                </label>
                <select
                  id="user-role"
                  required
                  className="form-input"
                  value={formData.role_id}
                  onChange={(e) => setFormData({ ...formData, role_id: e.target.value })}
                  data-testid="user-role-select"
                >
                  <option value="" disabled>
                    Select an assigned role...
                  </option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} {r.is_system ? '(System)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '16px 0' }}>
                <input
                  id="user-active-toggle"
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  data-testid="user-active-toggle"
                />
                <label htmlFor="user-active-toggle" style={{ fontSize: '13px', fontWeight: 500 }}>
                  Account Active and Permitted to Authenticate
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" data-testid="user-modal-submit">
                  Save Account
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
