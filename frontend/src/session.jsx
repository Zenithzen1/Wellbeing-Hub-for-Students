import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, demo, setMode } from './api/index.js';

const SessionCtx = createContext(null);
export const useSession = () => useContext(SessionCtx);

export function SessionProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = still checking, null = signed out
  const [mode, setModeState] = useState(api.mode);

  useEffect(() => {
    let alive = true;
    const restore = api.mode === 'demo' ? demo.restore() : api.me().catch(() => null);
    restore.then((u) => { if (alive) setUser(u || null); });
    return () => { alive = false; };
  }, []);

  const signInDemo = useCallback(async (role) => {
    setMode('demo'); setModeState('demo');
    const u = await demo.signInAs(role);
    setUser(u);
    return u;
  }, []);

  const signIn = useCallback(async (email, password, { create = false } = {}) => {
    setMode('live'); setModeState('live');
    if (create) await api.register(email, password);
    await api.login(email, password);
    const u = await api.me();
    setUser(u);
    return u;
  }, []);

  const signOut = useCallback(async () => {
    try { await api.logout(); } catch { /* the cookie may already be gone */ }
    setUser(null);
  }, []);

  return <SessionCtx.Provider value={{ user, mode, signIn, signInDemo, signOut }}>{children}</SessionCtx.Provider>;
}

export const HOME = { S: '/book', C: '/today', A: '/manage' };
