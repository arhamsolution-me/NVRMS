import React from 'react';
import { Settings } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  return (
    <div data-testid="settings-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">System Settings & DR</h1>
          <p className="page-description">Platform configuration, automated backup policies, and disaster recovery</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Settings size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>System Configuration & Backups</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Execute encrypted database backups, verify DR restoration integrity, and review retention schedules.
        </p>
      </div>
    </div>
  );
};
