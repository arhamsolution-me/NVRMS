import React from 'react';
import { Camera } from 'lucide-react';

export const DevicesPage: React.FC = () => {
  return (
    <div data-testid="devices-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">NVR & Camera Management</h1>
          <p className="page-description">Onboard NVRs by IP and discover IP cameras</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <Camera size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>NVR and Camera Inventory</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Onboard edge NVRs, trigger discovery probes, and inspect channels.
        </p>
      </div>
    </div>
  );
};
