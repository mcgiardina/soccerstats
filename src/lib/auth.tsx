import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ADMIN_EMAIL, supabase } from "./supabase";

interface AuthState {
  isAdmin: boolean;
  ready: boolean;
  login: (password: string) => Promise<string | null>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState>({ isAdmin: false, ready: false, login: async () => null, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setIsAdmin(Boolean(data.session));
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => setIsAdmin(Boolean(session)));
    return () => sub.subscription.unsubscribe();
  }, []);

  async function login(password: string): Promise<string | null> {
    if (!ADMIN_EMAIL) return "VITE_ADMIN_EMAIL is not set.";
    const { error } = await supabase.auth.signInWithPassword({ email: ADMIN_EMAIL, password });
    return error ? error.message : null;
  }

  async function logout() {
    await supabase.auth.signOut();
  }

  return <Ctx.Provider value={{ isAdmin, ready, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
