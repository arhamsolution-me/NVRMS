import React from 'react';
import { FileText } from 'lucide-react';

export const AuditPage: React.FC = () => {
  return (
    <div data-testid="audit-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Security & Audit Logs</h1>
          <p className="page-description">Immutable log of security events and administrative actions</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <FileText size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>Security Audit Trail</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Inspect user logins, lockout triggers, permission toggles, and stream sessions.
        </p>
      </div>
    </div>
  );
};
