import type { User, WorkspaceSummary } from "@gigscout/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { api, isUnauthorized } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  /** The workspace every page works in. */
  workspace: WorkspaceSummary | null;
  workspaces: WorkspaceSummary[];
  /** Owner or admin of the current workspace. */
  isAdmin: boolean;
  /** Runs the whole installation: every workspace, system health and configuration. */
  isPlatformAdmin: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  switchWorkspace: (id: number) => void;
}

const AuthContext = createContext<AuthState | null>(null);
const ME_KEY = ["auth", "me"] as const;
const WORKSPACE_KEY = "gs-workspace";

function remembered(): number | null {
  try {
    const value = Number(localStorage.getItem(WORKSPACE_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function remember(id: number) {
  try {
    localStorage.setItem(WORKSPACE_KEY, String(id));
  } catch {
    // private mode or blocked storage: the choice simply is not remembered
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<number | null>(remembered);
  const me = useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.auth.me();
      } catch (error) {
        if (isUnauthorized(error)) return null;
        throw error;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

  const workspaces = useMemo(() => me.data?.workspaces ?? [], [me.data]);
  const workspace = workspaces.find((w) => w.id === chosen) ?? workspaces[0] ?? null;
  api.setWorkspace(workspace?.id ?? null); // before any child query runs in this render

  const login = useCallback(
    async (email: string, password: string) => {
      const { user } = await api.auth.login(email, password);
      queryClient.setQueryData(ME_KEY, user);
      return user;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    await api.auth.logout();
    queryClient.clear();
    queryClient.setQueryData(ME_KEY, null);
  }, [queryClient]);

  const switchWorkspace = useCallback(
    (id: number) => {
      api.setWorkspace(id);
      remember(id);
      setChosen(id);
      // everything cached belongs to the previous workspace; keep only who is signed in
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_KEY[0] });
    },
    [queryClient],
  );

  const value = useMemo<AuthState>(
    () => ({
      user: me.data ?? null,
      loading: me.isPending,
      workspace,
      workspaces,
      isAdmin: workspace?.role === "owner" || workspace?.role === "admin",
      isPlatformAdmin: me.data?.role === "admin",
      login,
      logout,
      switchWorkspace,
    }),
    [me.data, me.isPending, workspace, workspaces, login, logout, switchWorkspace],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
