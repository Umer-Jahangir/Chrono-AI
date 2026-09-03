import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  ApiError,
  UNAUTHORIZED_EVENT,
  chronoApi,
  clearAccessToken,
  getAccessToken,
  storeAccessToken,
} from '../lib/apiClient';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('checking');
  const [user, setUser] = useState(null);
  const [message, setMessage] = useState('');

  const restoreSession = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setStatus('signedOut');
      return;
    }
    setStatus('checking');
    setMessage('');
    try {
      const currentUser = await chronoApi.me();
      setUser(currentUser);
      setStatus('authenticated');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAccessToken();
        setUser(null);
        setMessage('Your session expired. Please sign in again.');
        setStatus('signedOut');
      } else {
        setMessage(error.message || 'Chrono could not verify your session.');
        setStatus('error');
      }
    }
  }, []);

  useEffect(() => {
    const task = window.setTimeout(restoreSession, 0);
    return () => window.clearTimeout(task);
  }, [restoreSession]);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      setMessage('Your session expired. Please sign in again.');
      setStatus('signedOut');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const loginWithGoogleCredential = useCallback(async (credential) => {
    setStatus('signingIn');
    setMessage('');
    try {
      const session = await chronoApi.exchangeGoogleCredential(credential);
      if (!session?.access_token) {
        throw new ApiError('Chrono returned an invalid login response.');
      }
      storeAccessToken(session.access_token);
      const currentUser = await chronoApi.me();
      setUser(currentUser);
      setStatus('authenticated');
      return currentUser;
    } catch (error) {
      const unauthorized = error instanceof ApiError && error.status === 401;
      if (unauthorized) clearAccessToken();
      setUser(null);
      setMessage(error.message || 'Sign-in failed. Please try again.');
      setStatus(unauthorized ? 'signedOut' : 'error');
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    clearAccessToken();
    window.google?.accounts?.id?.disableAutoSelect?.();
    setUser(null);
    setMessage('You have signed out.');
    setStatus('signedOut');
  }, []);

  const value = useMemo(() => ({
    status,
    user,
    message,
    loginWithGoogleCredential,
    logout,
    restoreSession,
  }), [status, user, message, loginWithGoogleCredential, logout, restoreSession]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// This hook intentionally shares the provider module so all consumers use one context.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
