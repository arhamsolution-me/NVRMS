import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Video,
  MapPin,
  Camera,
  Cpu,
  Users,
  Shield,
  FileText,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface NavItemDef {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_ITEMS: NavItemDef[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/live', label: 'Live Monitor', icon: Video },
  { to: '/locations', label: 'Locations', icon: MapPin },
  { to: '/devices', label: 'NVRs & Cameras', icon: Camera },
  { to: '/agents', label: 'Edge Agents', icon: Cpu },
  { to: '/users', label: 'Users & Scopes', icon: Users },
  { to: '/roles', label: 'Roles & RBAC', icon: Shield },
  { to: '/audit', label: 'Audit Logs', icon: FileText },
  { to: '/settings', label: 'System Settings', icon: Settings },
];

export const Sidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState<boolean>(false);

  return (
    <aside
      className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}
      data-testid="app-sidebar"
    >
      <div className="sidebar-header">
        <div className="brand-wrapper">
          <div className="brand-logo" aria-hidden="true">
            N
          </div>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <span className="brand-text">NVRSMS</span>
              <span className="brand-sub">HUB</span>
            </div>
          )}
        </div>

        <button
          onClick={() => setCollapsed(!collapsed)}
          style={{
            color: 'var(--text-on-dark-muted)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4px',
            borderRadius: 'var(--radius-sm)',
          }}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          data-testid="sidebar-toggle-button"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      <nav className="sidebar-nav">
        {!collapsed && <div className="nav-section-title">Navigation</div>}

        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
              title={collapsed ? item.label : undefined}
              data-testid={`nav-link-${item.label.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
            >
              <Icon size={18} className="icon" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        {!collapsed ? (
          <>
            <span>NVRSMS Platform</span>
            <span style={{ fontSize: '10px', color: 'var(--color-primary-light)' }}>v0.1.0</span>
          </>
        ) : (
          <span style={{ width: '100%', textAlign: 'center', fontSize: '10px' }}>v0.1</span>
        )}
      </div>
    </aside>
  );
};
