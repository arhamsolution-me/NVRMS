import React from 'react';
import { Cpu } from 'lucide-react';

export const AgentsPage: React.FC = () => {
  return (
    <div data-testid="agents-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Edge Agents</h1>
          <p className="page-description">Manage enrolled Edge Agents, health heartbeats, and OTA upgrades</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Cpu size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>Edge Agent Fleet</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Generate single-use enrolment codes and monitor fleet connectivity.
        </p>
      </div>
    </div>
  );
};
