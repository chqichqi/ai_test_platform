import React from 'react';
import { Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { selectToken, selectUser, hasAnyPermission, hasAnyRole } from '../../store/slices/authSlice';

type UserRole = 'external' | 'tester' | 'test_engineer' | 'test_manager' | 'admin';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPermissions?: string[];
  requiredRoles?: UserRole[];
  requireAll?: boolean;
  fallbackPath?: string;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredPermissions = [],
  requiredRoles = [],
  requireAll = false,
  fallbackPath = '/dashboard',
}) => {
  const token = useSelector(selectToken);
  const user = useSelector(selectUser);

  if (!token) {
    return <Navigate to="/auth/login" replace />;
  }

  if (user?.is_superuser) {
    return <>{children}</>;
  }

  if (requiredRoles.length > 0) {
    const state = { auth: { user, token, refreshToken: null } };
    const hasRequiredRole = hasAnyRole(state as any, requiredRoles);
    if (!hasRequiredRole) {
      return <Navigate to={fallbackPath} replace />;
    }
  }

  if (requiredPermissions.length > 0) {
    const state = { auth: { user, token, refreshToken: null } };
    const hasRequiredPermission = requireAll
      ? requiredPermissions.every(p => user?.permissions?.includes(p))
      : hasAnyPermission(state as any, requiredPermissions);
    if (!hasRequiredPermission) {
      return <Navigate to={fallbackPath} replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;