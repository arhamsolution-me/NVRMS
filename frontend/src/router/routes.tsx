import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { DashboardPage } from '../pages/DashboardPage';
import { LiveMonitorPage } from '../pages/LiveMonitorPage';
import { LocationsPage } from '../pages/LocationsPage';
import { DevicesPage } from '../pages/DevicesPage';
import { AgentsPage } from '../pages/AgentsPage';
import { UsersPage } from '../pages/UsersPage';
import { RolesPage } from '../pages/RolesPage';
import { AuditPage } from '../pages/AuditPage';
import { SettingsPage } from '../pages/SettingsPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { AppLayout } from '../components/layout/AppLayout';
import { ProtectedRoute } from '../components/common/ProtectedRoute';
import { PermissionRoute } from '../components/common/PermissionRoute';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Authenticated Application Shell */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="live" element={<LiveMonitorPage />} />
        <Route path="locations" element={<LocationsPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="agents" element={<AgentsPage />} />

        {/* Permission Guarded Routes */}
        <Route
          path="users"
          element={
            <PermissionRoute permission="users:read">
              <UsersPage />
            </PermissionRoute>
          }
        />
        <Route
          path="roles"
          element={
            <PermissionRoute permission="roles:read">
              <RolesPage />
            </PermissionRoute>
          }
        />
        <Route
          path="audit"
          element={
            <PermissionRoute permission="audit:read">
              <AuditPage />
            </PermissionRoute>
          }
        />
        <Route
          path="settings"
          element={
            <PermissionRoute permission="settings:read">
              <SettingsPage />
            </PermissionRoute>
          }
        />

        {/* Catch-all 404 inside app shell */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
};
