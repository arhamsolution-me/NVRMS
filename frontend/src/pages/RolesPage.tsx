import React from 'react';
import { Shield } from 'lucide-react';

export const RolesPage: React.FC = () => {
  return (
    <div data-testid="roles-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Roles & RBAC Matrix</h1>
          <p className="page-description">Configure dynamic roles and toggle permission flags instantly</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Shield size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>Roles & Permission Matrix</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Real-time permission toggle engine with instant Redis cache invalidation.
        </p>
      </div>
    </div>
  );
};
