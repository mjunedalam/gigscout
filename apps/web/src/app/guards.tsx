import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { ShellSkeleton } from "../components/skeletons";
import { useAuth } from "../lib/auth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return <ShellSkeleton />;
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

/** The API enforces roles too; this only keeps members away from screens that would 403. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/" replace />;
}

/** System health and configuration cover the whole installation, so only platform admins see them. */
export function RequirePlatformAdmin({ children }: { children: ReactNode }) {
  const { isPlatformAdmin } = useAuth();
  return isPlatformAdmin ? children : <Navigate to="/" replace />;
}
