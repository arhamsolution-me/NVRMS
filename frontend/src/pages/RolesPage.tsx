import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import {
  Shield,
  Plus,
  Trash2,
  CheckCircle,
  XCircle,
  Lock,
  Layers,
  Search,
} from 'lucide-react';

interface RoleItem {
  id: string;
  name: string;
  description?: string;
  is_system: boolean;
}

interface PermissionItem {
  permission_id: string;
  code: string;
  name: string;
  module: string;
  is_granted: boolean;
}

export const RolesPage: React.FC = () => {
  const { hasPermission } = useAuth();
  const { showToast } = useToast();

  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [selectedRole, setSelectedRole] = useState<RoleItem | null>(null);
  const [permissions, setPermissions] = useState<PermissionItem[]>([]);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleDesc, setNewRoleDesc] = useState('');

  const fetchRoles = useCallback(async () => {
    try {
      setLoadingRoles(true);
      const data = await api.get<RoleItem[]>('/roles');
      setRoles(data);
      if (data.length > 0 && !selectedRole) {
        setSelectedRole(data[0]);
      }
    } catch {
      showToast('Failed to load roles list', 'error');
    } finally {
      setLoadingRoles(false);
    }
  }, [selectedRole, showToast]);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  const fetchPermissions = useCallback(async (roleId: string) => {
    try {
      setLoadingPerms(true);
      const data = await api.get<PermissionItem[]>(`/roles/${roleId}/permissions`);
      setPermissions(data);
    } catch {
      showToast('Failed to load permissions matrix', 'error');
    } finally {
      setLoadingPerms(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (selectedRole) {
      fetchPermissions(selectedRole.id);
    }
  }, [selectedRole, fetchPermissions]);

  const handleToggle = async (perm: PermissionItem) => {
    if (!selectedRole) return;
    const nextGranted = !perm.is_granted;

    // Optimistically update UI
    setPermissions((prev) =>
      prev.map((p) => (p.code === perm.code ? { ...p, is_granted: nextGranted } : p))
    );

    try {
      await api.put(`/roles/${selectedRole.id}/permissions`, {
        permission_code: perm.code,
        is_granted: nextGranted,
      });
      showToast(
        `${perm.name} ${nextGranted ? 'granted to' : 'revoked from'} ${selectedRole.name}`,
        'success'
      );
    } catch (err: unknown) {
      // Revert on error
      setPermissions((prev) =>
        prev.map((p) => (p.code === perm.code ? { ...p, is_granted: perm.is_granted } : p))
      );
      showToast((err as Error).message || 'Failed to update permission', 'error');
    }
  };

  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await api.post<RoleItem>('/roles', {
        name: newRoleName,
        description: newRoleDesc,
      });
      showToast(`Role "${created.name}" created`, 'success');
      setIsModalOpen(false);
      setNewRoleName('');
      setNewRoleDesc('');
      await fetchRoles();
      setSelectedRole(created);
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to create role', 'error');
    }
  };

  const handleDeleteRole = async (role: RoleItem) => {
    if (role.is_system) {
      showToast('System roles are immutable and cannot be deleted', 'warning');
      return;
    }
    if (!window.confirm(`Delete custom role "${role.name}"?`)) return;

    try {
      await api.delete(`/roles/${role.id}`);
      showToast(`Role "${role.name}" deleted`, 'success');
      setSelectedRole(null);
      await fetchRoles();
    } catch (err: unknown) {
      showToast((err as Error).message || 'Failed to delete role', 'error');
    }
  };

  // Group permissions by module
  const groupedPermissions: Record<string, PermissionItem[]> = {};
  permissions.forEach((p) => {
    const mod = p.module.toUpperCase();
    if (!groupedPermissions[mod]) {
      groupedPermissions[mod] = [];
    }
    if (!searchQuery || p.name.toLowerCase().includes(searchQuery.toLowerCase()) || p.code.toLowerCase().includes(searchQuery.toLowerCase())) {
      groupedPermissions[mod].push(p);
    }
  });

  return (
    <div data-testid="roles-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Roles & RBAC Matrix</h1>
          <p className="page-description">
            Role definitions and real-time permission toggle engine with instant Redis cache invalidation
          </p>
        </div>
        {hasPermission('roles:write') && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="btn btn-primary"
            data-testid="create-role-btn"
          >
            <Plus size={16} /> New Custom Role
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) 2fr', gap: '20px' }}>
        {/* Roles List Card */}
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '14px' }}>
            ASSIGNABLE ROLES
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {loadingRoles ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading roles...</p>
            ) : (
              roles.map((role) => (
                <div
                  key={role.id}
                  onClick={() => setSelectedRole(role)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid',
                    borderColor:
                      selectedRole?.id === role.id ? 'var(--color-primary)' : 'var(--border-subtle)',
                    backgroundColor:
                      selectedRole?.id === role.id ? 'var(--color-primary-light)' : 'var(--bg-surface)',
                    cursor: 'pointer',
                    transition: 'all var(--transition-fast)',
                  }}
                  data-testid={`role-card-${role.id}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Shield
                      size={18}
                      color={selectedRole?.id === role.id ? 'var(--color-primary)' : 'var(--text-muted)'}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                        {role.name}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {role.description || (role.is_system ? 'System Defined Role' : 'Custom Organization Role')}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {role.is_system ? (
                      <span className="badge badge-info" style={{ fontSize: '10px' }} title="System Protected">
                        <Lock size={10} /> System
                      </span>
                    ) : (
                      hasPermission('roles:write') && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteRole(role);
                          }}
                          style={{ color: 'var(--status-offline)', padding: '2px 4px' }}
                          title="Delete Custom Role"
                          data-testid={`delete-role-${role.id}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      )
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Permissions Matrix Card */}
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column' }}>
          {selectedRole ? (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '16px',
                  marginBottom: '20px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0 }}>
                      Permissions for {selectedRole.name}
                    </h2>
                    {selectedRole.is_system && (
                      <span className="badge badge-info" style={{ fontSize: '11px' }}>
                        System Role
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Toggles trigger instantaneous permission cache invalidation across the cluster.
                  </p>
                </div>

                <div style={{ position: 'relative', width: '220px' }}>
                  <Search
                    size={14}
                    color="var(--text-muted)"
                    style={{ position: 'absolute', left: '10px', top: '9px' }}
                  />
                  <input
                    type="text"
                    placeholder="Filter permissions..."
                    className="form-input"
                    style={{ paddingLeft: '32px', fontSize: '12px' }}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    data-testid="filter-permissions-input"
                  />
                </div>
              </div>

              {loadingPerms ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                  Loading permissions matrix...
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto' }}>
                  {Object.entries(groupedPermissions).map(([moduleName, perms]) => (
                    <div key={moduleName} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <div
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          letterSpacing: '0.06em',
                          color: 'var(--text-muted)',
                          paddingBottom: '4px',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                      >
                        {moduleName} PERMISSIONS ({perms.filter((p) => p.is_granted).length}/{perms.length})
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        {perms.map((perm) => (
                          <div
                            key={perm.code}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              padding: '10px 14px',
                              borderRadius: 'var(--radius-md)',
                              backgroundColor: perm.is_granted
                                ? 'var(--status-online-bg)'
                                : 'var(--bg-surface-subtle)',
                              border: '1px solid',
                              borderColor: perm.is_granted
                                ? 'rgba(16, 185, 129, 0.25)'
                                : 'var(--border-subtle)',
                              transition: 'all var(--transition-fast)',
                            }}
                            data-testid={`perm-row-${perm.code}`}
                          >
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                {perm.name}
                              </span>
                              <code
                                style={{
                                  fontSize: '11px',
                                  color: 'var(--text-muted)',
                                  fontFamily: 'var(--font-mono)',
                                }}
                              >
                                {perm.code}
                              </code>
                            </div>

                            <button
                              onClick={() => handleToggle(perm)}
                              disabled={!hasPermission('roles:manage_permissions')}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                padding: '4px 8px',
                                borderRadius: 'var(--radius-full)',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                backgroundColor: perm.is_granted ? 'var(--status-online)' : 'var(--border-medium)',
                                color: '#ffffff',
                                border: 'none',
                                transition: 'background-color var(--transition-fast)',
                              }}
                              data-testid={`toggle-${perm.code}`}
                              aria-label={`Toggle permission ${perm.code}`}
                            >
                              {perm.is_granted ? <CheckCircle size={14} /> : <XCircle size={14} />}
                              <span>{perm.is_granted ? 'Granted' : 'Revoked'}</span>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
              <Layers size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Select a Role</h3>
              <p style={{ fontSize: '13px', marginTop: '4px' }}>
                Select any role from the left pane to inspect and customize its permissions matrix.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Create Role Modal */}
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
          data-testid="create-role-modal"
        >
          <div className="card" style={{ width: '420px', padding: '24px', backgroundColor: '#ffffff' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>
              Create Custom Role
            </h3>

            <form onSubmit={handleCreateRole}>
              <div className="form-group">
                <label className="form-label" htmlFor="role-name">
                  Role Name
                </label>
                <input
                  id="role-name"
                  type="text"
                  required
                  className="form-input"
                  placeholder="e.g. Branch Supervisor"
                  value={newRoleName}
                  onChange={(e) => setNewRoleName(e.target.value)}
                  data-testid="role-name-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="role-description">
                  Description
                </label>
                <input
                  id="role-description"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Can view cameras and manage local users"
                  value={newRoleDesc}
                  onChange={(e) => setNewRoleDesc(e.target.value)}
                  data-testid="role-description-input"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" data-testid="role-modal-submit">
                  Save Role
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
