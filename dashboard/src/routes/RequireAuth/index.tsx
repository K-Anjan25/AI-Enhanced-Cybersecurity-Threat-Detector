import React from "react";
import { Navigate, Outlet, useLocation, Location } from "react-router-dom";
import { getToken } from "../../utils/token";

export interface RequireAuthProps {
  allowedRoles?: string[];
  allowedPermissions?: string[];
  roles?: string[] | string;
  permissions?: string[] | string;
}

const asArray = (value: string[] | string | undefined): string[] => {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") return [value];
  return [];
};

const RequireAuth: React.FC<RequireAuthProps> = ({
  allowedRoles = [],
  allowedPermissions = [],
  roles = [],
  permissions = [],
}) => {
  const location: Location = useLocation();

  const userRoles: string[] = asArray(roles);
  const userPermissions: string[] = asArray(permissions);

  // ABAC: permission-based access when allowedPermissions are specified.
  const hasPermissionAccess: boolean =
    allowedPermissions.length === 0 ||
    allowedPermissions.some((perm: string) => userPermissions.includes(perm));

  const hasRoleAccess: boolean =
    allowedRoles.length === 0 ||
    allowedRoles.some((role: string) => userRoles.includes(role));

  // Tokens live in httpOnly cookies (set by the backend); the non-sensitive
  // auth flag is what JS can read to gate routes.
  if (!getToken()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!hasPermissionAccess || !hasRoleAccess) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  return <Outlet />;
};

export default RequireAuth;
