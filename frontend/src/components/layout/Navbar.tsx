import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { LogOut, ShieldCheck, Building2, User as UserIcon } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { user, tenant, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const getInitials = (email?: string, name?: string) => {
    if (name) return name.substring(0, 2).toUpperCase();
    if (email) return email.substring(0, 2).toUpperCase();
    return 'U';
  };

  return (
    <header className="top-navbar" data-testid="top-navbar">
      <div className="navbar-left">
        <div className="tenant-badge" data-testid="tenant-badge">
          <Building2 size={16} color="var(--color-primary)" />
          <span>{tenant?.name || 'Default Organization'}</span>
        </div>

        <div
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}
          title="Hub Live Telemetry Active"
        >
          <span className="ws-status-dot connected" data-testid="ws-status-dot" />
          <span style={{ fontWeight: 500 }}>Live</span>
        </div>
      </div>

      <div className="navbar-right">
        {user?.is_superuser && (
          <span
            className="badge badge-info"
            style={{ fontWeight: 600, letterSpacing: '0.02em' }}
            data-testid="superuser-tag"
          >
            Super Admin
          </span>
        )}

        {user?.totp_enabled && (
          <span
            className="badge badge-online"
            style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
            title="Two-Factor Authentication Protected"
          >
            <ShieldCheck size={12} />
            2FA
          </span>
        )}

        <div style={{ position: 'relative' }}>
          <button
            className="user-profile-btn"
            onClick={() => setMenuOpen(!menuOpen)}
            data-testid="user-profile-menu-button"
            aria-expanded={menuOpen}
          >
            <div className="user-avatar">{getInitials(user?.email, user?.name)}</div>
            <div className="user-meta">
              <span className="user-name">{user?.name || user?.email?.split('@')[0]}</span>
              <span className="user-role">{user?.role_name || (user?.is_superuser ? 'Root Admin' : 'Operator')}</span>
            </div>
          </button>

          {menuOpen && (
            <div
              className="card"
              style={{
                position: 'absolute',
                top: 'calc(100% + 8px)',
                right: 0,
                width: '240px',
                padding: '8px',
                zIndex: 50,
                boxShadow: 'var(--shadow-xl)',
              }}
              data-testid="user-dropdown-menu"
            >
              <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)', marginBottom: '6px' }}>
                <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{user?.email}</p>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tenant ID: {tenant?.id?.substring(0, 8)}...</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 12px',
                    fontSize: '13px',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <UserIcon size={14} /> Profile Scopes: {user?.scopes?.length || 0}
                </div>

                <button
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                  className="btn"
                  style={{
                    width: '100%',
                    justifyContent: 'flex-start',
                    color: 'var(--status-offline)',
                    padding: '8px 12px',
                    fontSize: '13px',
                  }}
                  data-testid="logout-button"
                >
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
