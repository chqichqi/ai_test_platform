import { useSelector } from 'react-redux';
import {
  selectUser,
  selectPermissions,
  selectRoles,
  selectIsSuperuser,
} from '../store/slices/authSlice';

type UserRole = 'external' | 'tester' | 'test_engineer' | 'test_manager' | 'admin';

export const usePermissions = () => {
  const user = useSelector(selectUser);
  const permissions = useSelector(selectPermissions);
  const roles = useSelector(selectRoles);
  const isSuperuser = useSelector(selectIsSuperuser);

  const checkPermission = (permission: string): boolean => {
    if (isSuperuser) return true;
    return permissions.includes(permission);
  };

  const checkAnyPermission = (perms: string[]): boolean => {
    if (isSuperuser) return true;
    return perms.some(p => permissions.includes(p));
  };

  const checkAllPermissions = (perms: string[]): boolean => {
    if (isSuperuser) return true;
    return perms.every(p => permissions.includes(p));
  };

  const checkRole = (role: UserRole): boolean => {
    if (isSuperuser) return true;
    return roles.includes(role);
  };

  const checkAnyRole = (rs: UserRole[]): boolean => {
    if (isSuperuser) return true;
    return rs.some(r => roles.includes(r));
  };

  const canCreate = (module: string): boolean => checkPermission(`${module}:create`);
  const canRead = (module: string): boolean => checkPermission(`${module}:read`);
  const canUpdate = (module: string): boolean => checkPermission(`${module}:update`);
  const canDelete = (module: string): boolean => checkPermission(`${module}:delete`);
  const canExecute = (module: string): boolean => checkPermission(`${module}:execute`);

  const isExternal = (): boolean => roles.includes('external') && !isSuperuser;
  const isTester = (): boolean => roles.includes('tester') && !isSuperuser;
  const isTestEngineer = (): boolean => roles.includes('test_engineer') && !isSuperuser;
  const isTestManager = (): boolean => roles.includes('test_manager') && !isSuperuser;
  const isAdmin = (): boolean => isSuperuser;

  return {
    user,
    permissions,
    roles,
    isSuperuser,
    checkPermission,
    checkAnyPermission,
    checkAllPermissions,
    checkRole,
    checkAnyRole,
    canCreate,
    canRead,
    canUpdate,
    canDelete,
    canExecute,
    isExternal,
    isTester,
    isTestEngineer,
    isTestManager,
    isAdmin,
  };
};