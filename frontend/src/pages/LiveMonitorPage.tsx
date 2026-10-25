import React from 'react';
import { Video } from 'lucide-react';

export const LiveMonitorPage: React.FC = () => {
  return (
    <div data-testid="live-monitor-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Live Video Monitor</h1>
          <p className="page-description">Multi-camera real-time surveillance grid (1x1, 2x2, 3x3, 4x4)</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Video size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>Live Video Grid Ready</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px', maxWidth: '480px', margin: '8px auto 0' }}>
          Select cameras from the location tree to commence low-latency WebRTC streaming.
        </p>
      </div>
    </div>
  );
};
