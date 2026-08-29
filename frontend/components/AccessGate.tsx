'use client';

import { FormEvent, ReactNode, useEffect, useState } from 'react';
import { ACCESS_TOKEN_KEY, api } from '@/lib/api';

export default function AccessGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'locked' | 'open'>('checking');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function checkAccess() {
      try {
        const status = await api.accessStatus();
        if (!status.enabled) {
          setState('open');
          return;
        }
        const token = window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
        if (!token) {
          setState('locked');
          return;
        }
        await api.verifyAccess();
        setState('open');
      } catch {
        window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
        setState('locked');
      }
    }
    void checkAccess();
  }, []);

  async function unlock(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const result = await api.unlockAccess(password);
      if (result.token) window.sessionStorage.setItem(ACCESS_TOKEN_KEY, result.token);
      setPassword('');
      setState('open');
    } catch {
      setError('That password is not correct.');
    } finally {
      setSubmitting(false);
    }
  }

  if (state === 'open') return <>{children}</>;
  if (state === 'checking') return <main className="access-screen"><div className="access-card"><span className="comparison-loader-mark" aria-hidden="true" /><p>Opening PolicyForge…</p></div></main>;

  return <main className="access-screen">
    <form className="access-card" onSubmit={unlock}>
      <div className="label">Private workspace</div>
      <h1>PolicyForge access</h1>
      <p>Enter the shared workspace password to open the simulator.</p>
      <label className="access-label" htmlFor="policyforge-password">Password</label>
      <input id="policyforge-password" className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus required />
      {error ? <p className="error-box">{error}</p> : null}
      <button className="btn primary access-submit" type="submit" disabled={submitting}>{submitting ? 'CHECKING…' : 'OPEN POLICYFORGE →'}</button>
      <small>Access expires when this browser session ends.</small>
    </form>
  </main>;
}
