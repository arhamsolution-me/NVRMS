import React from 'react';
import { ShieldAlert, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const AccessDenied: React.FC<{
  permissionCode?: string;
  message?: string;
}> = ({
  permissionCode,
  message = "You don't have the required permissions to view this module or resource.",
}) => {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        minHeight: '400px',
        textAlign: 'center',
        padding: '32px',
      }}
      data-testid="access-denied-view"
    >
      <div
        style={{
          width: '64px',
          height: '64px',
          borderRadius: 'var(--radius-full)',
          backgroundColor: 'var(--status-offline-bg)',
          color: 'var(--status-offline)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '20px',
          border: '1px solid rgba(239, 68, 68, 0.2)',
        }}
      >
        <ShieldAlert size={32} />
      </div>

      <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
        403 Access Denied
      </h2>

      <p style={{ maxWidth: '440px', color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6, marginBottom: '16px' }}>
        {message}
      </p>

      {permissionCode && (
        <div style={{ marginBottom: '24px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginRight: '6px' }}>Required permission:</span>
          <code
            style={{
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-subtle)',
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-primary)',
            }}
          >
            {permissionCode}
          </code>
        </div>
      )}

      <button
        onClick={() => navigate('/dashboard')}
        className="btn btn-secondary"
        style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
      >
        <ArrowLeft size={16} /> Return to Dashboard
      </button>
    </div>
  );
};
