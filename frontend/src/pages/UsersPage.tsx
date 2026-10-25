import React from 'react';
import { Users } from 'lucide-react';

export const UsersPage: React.FC = () => {
  return (
    <div data-testid="users-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Users & Scopes</h1>
          <p className="page-description">Manage user accounts, location scopes, and TOTP 2FA enforcement</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Users size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>User Management</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Assign granular roles and location scoping (Province, City, Area, Site).
        </p>
      </div>
    </div>
  );
};
