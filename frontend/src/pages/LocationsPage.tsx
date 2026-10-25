import React from 'react';
import { MapPin } from 'lucide-react';

export const LocationsPage: React.FC = () => {
  return (
    <div data-testid="locations-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Location Hierarchy</h1>
          <p className="page-description">Geographic tree management (Province &gt; City &gt; Area &gt; Site)</p>
        </div>
      </div>
      <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
        <MapPin size={48} color="var(--color-primary)" style={{ margin: '0 auto 16px' }} />
        <h3 style={{ fontSize: '18px', fontWeight: 700 }}>Location Hierarchy Manager</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          Hierarchical location tree and site management module.
        </p>
      </div>
    </div>
  );
};
