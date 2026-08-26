import React from 'react';
import { useSelector } from 'react-redux';
import { selectUser, hasAnyPermission } from '../../store/slices/authSlice';

type UserRole = 'external' | 'tester' | 'test_engineer' | 'test_manager' | 'admin';

interface PermissionGuardProps {
  children: React.ReactNode;
  requiredPermissions?: string[];
  requiredRoles?: UserRole[];
  requireAll?: boolean;
  fallback?: React.ReactNode;
}

const PermissionGuard: React.FC<PermissionGuardProps> = ({
  children,
  requiredPermissions = [],
  requiredRoles = [],
  requireAll = false,
  fallback = null,
}) => {
  const user = useSelector(selectUser);

  if (!user) {
    return <>{fallback}</>;
  }

  if (user.is_superuser) {
    return <>{children}</>;
  }

  if (requiredRoles.length > 0) {
    const hasRequiredRole = requiredRoles.some(role => user.roles?.includes(role));
    if (!hasRequiredRole) {
      return <>{fallback}</>;
    }
  }

  if (requiredPermissions.length > 0) {
    const state = { auth: { user, token: null, refreshToken: null } };
    const hasRequiredPermission = requireAll
      ? requiredPermissions.every(p => user.permissions?.includes(p))
      : hasAnyPermission(state as any, requiredPermissions);
    if (!hasRequiredPermission) {
      return <>{fallback}</>;
    }
  }

  return <>{children}</>;
};

export default PermissionGuard;

export const CanCreate: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:create`]}>{children}</PermissionGuard>
);

export const CanUpdate: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:update`]}>{children}</PermissionGuard>
);

export const CanDelete: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:delete`]}>{children}</PermissionGuard>
);

export const CanExecute: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:execute`]}>{children}</PermissionGuard>
);

export const CanRead: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:read`]}>{children}</PermissionGuard>
);

export const CanManage: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => (
  <PermissionGuard requiredPermissions={[`${module}:create`, `${module}:update`, `${module}:delete`]} requireAll={false}>
    {children}
  </PermissionGuard>
);

export const ForRoles: React.FC<{ children: React.ReactNode; roles: UserRole[] }> = ({ children, roles }) => (
  <PermissionGuard requiredRoles={roles}>{children}</PermissionGuard>
);