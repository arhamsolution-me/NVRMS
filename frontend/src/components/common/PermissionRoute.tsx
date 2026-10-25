import React from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { AccessDenied } from './AccessDenied';
import { LoadingSpinner } from './LoadingSpinner';

export const PermissionRoute: React.FC<{
  permission: string;
  children?: React.ReactNode;
}> = ({ permission, children }) => {
  const { hasPermission, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner size={24} label="Verifying access rights..." />;
  }

  if (!hasPermission(permission)) {
    return <AccessDenied permissionCode={permission} />;
  }

  return children ? <>{children}</> : <Outlet />;
};
