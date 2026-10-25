import React from 'react';
import { useAuth } from '../context/AuthContext';
import { Video, Cpu, Camera, Activity, CheckCircle, Shield } from 'lucide-react';
import { Link } from 'react-router-dom';

export const DashboardPage: React.FC = () => {
  const { user, tenant } = useAuth();

  return (
    <div data-testid="dashboard-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Operational Dashboard</h1>
          <p className="page-description">
            Live telemetry and system health overview for {tenant?.name || 'Primary Tenant'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Link to="/live" className="btn btn-primary" data-testid="goto-live-monitor-btn">
            <Video size={16} /> Open Live Monitor
          </Link>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '20px',
          marginBottom: '28px',
        }}
      >
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>ACTIVE STREAMS</span>
            <div style={{ padding: '8px', borderRadius: '8px', backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
              <Video size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '12px' }} data-testid="metric-active-streams">
            0
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            <span className="badge badge-online">On-Demand</span>
            <span>Viewer fan-out active</span>
          </div>
        </div>

        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>EDGE AGENTS</span>
            <div style={{ padding: '8px', borderRadius: '8px', backgroundColor: 'var(--status-online-bg)', color: 'var(--status-online)' }}>
              <Cpu size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '12px' }} data-testid="metric-online-agents">
            1
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            <span className="badge badge-online">Connected</span>
            <span>Heartbeats healthy</span>
          </div>
        </div>

        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>ONLINE CAMERAS</span>
            <div style={{ padding: '8px', borderRadius: '8px', backgroundColor: 'var(--status-info-bg)', color: 'var(--status-info)' }}>
              <Camera size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '12px' }} data-testid="metric-total-cameras">
            4
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            <span className="badge badge-info">RTSP</span>
            <span>RTSP / WHIP relay</span>
          </div>
        </div>

        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>SYSTEM HEALTH</span>
            <div style={{ padding: '8px', borderRadius: '8px', backgroundColor: 'var(--status-online-bg)', color: 'var(--status-online)' }}>
              <Activity size={20} />
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: 'var(--status-online)', marginTop: '12px' }} data-testid="metric-health-status">
            100%
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--status-online)', marginTop: '8px' }}>
            <CheckCircle size={14} />
            <span>All systems nominal</span>
          </div>
        </div>
      </div>

      {/* User Session Banner */}
      <div
        className="card"
        style={{
          padding: '24px',
          background: 'linear-gradient(135deg, #ffffff, #f8fafc)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
            Welcome back, {user?.email}
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Role: <strong>{user?.is_superuser ? 'Super Administrator' : user?.role_name || 'Standard User'}</strong> |
            Location Scope: <strong>{user?.scopes?.length ? `${user.scopes.length} Scoped Area(s)` : 'Unrestricted Global'}</strong>
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Link to="/devices" className="btn btn-secondary">
            Manage Devices
          </Link>
          <Link to="/roles" className="btn btn-secondary">
            <Shield size={14} /> Permissions Matrix
          </Link>
        </div>
      </div>
    </div>
  );
};
