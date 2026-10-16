import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, setCsrf } from "./api";
import { useI18n } from "./i18n";
import type { Me } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: Me) => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();
  const { setLang } = useI18n();

  const refresh = useCallback(async () => {
    try {
      const r = await api.get<{ user: Me; csrf_token: string }>("/auth/me");
      setCsrf(r.csrf_token);
      setUser(r.user);
      setLang(r.user.locale);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [setLang]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.post<{ user: Me; csrf_token: string }>("/auth/login", { email, password });
      setCsrf(r.csrf_token);
      qc.clear();
      setUser(r.user);
      setLang(r.user.locale);
      return r.user;
    },
    [qc, setLang],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setCsrf(null);
      qc.clear();
      setUser(null);
    }
  }, [qc]);

  return <Ctx.Provider value={{ user, loading, login, logout, refresh, setUser }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("AuthProvider missing");
  return c;
}

/** Current user, asserted (use inside authenticated routes only). */
export function useMe(): Me {
  const { user } = useAuth();
  if (!user) throw new Error("not authenticated");
  return user;
}
