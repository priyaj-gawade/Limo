import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { User } from '../types';
import { useToast } from './ToastContext';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isLoginModalOpen: boolean;
  authError: string | null;
  openLoginModal: () => void;
  closeLoginModal: () => void;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
  clearAuthError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const { showToast } = useToast();
  const authedRef = useRef<boolean>(false);

  const clearAuthError = useCallback(() => {
    setAuthError(null);
  }, []);

  const openLoginModal = useCallback(() => {
    setAuthError(null);
    setIsLoginModalOpen(true);
  }, []);

  const closeLoginModal = useCallback(() => {
    setIsLoginModalOpen(false);
  }, []);

  // Check current session from backend with 3.5s timeout to prevent UI hanging
  const checkSession = useCallback(async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    try {
      const res = await fetch('/api/v1/auth/me', {
        credentials: 'include',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data: User = await res.json();
        if (data && (data.provider === 'google' || data.provider === 'desktop')) {
          setUser(data);
          authedRef.current = true;
          setIsLoginModalOpen(false);
          setAuthError(null);
          return;
        }
      }
      setUser(null);
      authedRef.current = false;
      if (window.location.pathname !== '/auth/callback') {
        setIsLoginModalOpen(true);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.warn('Session check failed or timed out:', err?.message || err);
      setUser(null);
      authedRef.current = false;
      if (window.location.pathname !== '/auth/callback') {
        setIsLoginModalOpen(true);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Handle OAuth Callback if page loads at /auth/callback
  useEffect(() => {
    const handleCallbackRoute = async () => {
      if (window.location.pathname === '/auth/callback') {
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        const state = params.get('state');

        if (code && state) {
          try {
            const res = await fetch(`/api/v1/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`, {
              credentials: 'include',
            });
            if (res.ok) {
              const authedUser: User = await res.json();
              if (window.opener) {
                window.opener.postMessage(
                  { type: 'LIMO_AUTH_SUCCESS', user: authedUser },
                  window.location.origin
                );
                window.close();
                return;
              } else {
                setUser(authedUser);
                authedRef.current = true;
                window.history.replaceState({}, document.title, '/');
                showToast(`Signed in as ${authedUser.display_name || authedUser.email}`, 'success');
              }
            } else {
              const err = await res.json().catch(() => ({}));
              const errorText = err.detail || 'Google authentication failed';
              if (window.opener) {
                window.opener.postMessage(
                  { type: 'LIMO_AUTH_ERROR', error: errorText },
                  window.location.origin
                );
                window.close();
                return;
              }
              setAuthError(errorText);
              showToast(errorText, 'error');
              window.history.replaceState({}, document.title, '/');
            }
          } catch (err: any) {
            console.error('Callback error:', err);
            const msg = err?.message || 'Network error during Google sign-in';
            setAuthError(msg);
            if (window.opener) window.close();
            window.history.replaceState({}, document.title, '/');
          }
        }
      }
    };

    handleCallbackRoute();
  }, [showToast]);

  // Listen for popup messages from child OAuth window
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;

      if (event.data?.type === 'LIMO_AUTH_SUCCESS') {
        const loggedUser: User = event.data.user;
        setUser(loggedUser);
        authedRef.current = true;
        setIsLoginModalOpen(false);
        setAuthError(null);
        showToast(`Signed in as ${loggedUser.display_name || loggedUser.email}`, 'success');
      } else if (event.data?.type === 'LIMO_AUTH_ERROR') {
        const errMsg = event.data.error || 'Google authentication failed';
        setAuthError(errMsg);
        showToast(errMsg, 'error');
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [showToast]);

  // Initial session check on mount
  useEffect(() => {
    checkSession();
  }, [checkSession]);

  // Trigger Google OAuth sign-in flow
  const loginWithGoogle = async () => {
    setAuthError(null);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const res = await fetch('/api/v1/auth/login', {
        credentials: 'include',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || 'Failed to initialize Google authentication');
      }

      const data = await res.json();
      const authUrl = data.authorization_url;

      if (!authUrl) {
        throw new Error('No authorization URL returned by backend');
      }

      // Open a centered Google OAuth popup
      const width = 520;
      const height = 650;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const popup = window.open(
        authUrl,
        'limo_google_oauth',
        `width=${width},height=${height},left=${left},top=${top},status=no,menubar=no,toolbar=no`
      );

      if (!popup || popup.closed || typeof popup.closed === 'undefined') {
        // Fallback to full-window redirect if popup is blocked
        window.location.href = authUrl;
        return;
      }

      // Track popup closure
      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          setTimeout(() => {
            if (!authedRef.current) {
              checkSession().then(() => {
                if (!authedRef.current) {
                  setAuthError('Google sign-in window was closed without completing authorization.');
                }
              });
            }
          }, 800);
        }
      }, 500);
    } catch (err: any) {
      console.error('Google login error:', err);
      const errMsg = err?.message || 'Could not connect to Google sign-in';
      setAuthError(errMsg);
      showToast(errMsg, 'error');
    }
  };

  const logout = async () => {
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch (err) {
      console.warn('Logout error:', err);
    } finally {
      setUser(null);
      authedRef.current = false;
      setIsLoginModalOpen(true);
      showToast('Logged out successfully', 'info');
    }
  };

  const isAuthenticated = Boolean(user && (user.provider === 'google' || user.provider === 'desktop'));

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        isLoginModalOpen,
        authError,
        openLoginModal,
        closeLoginModal,
        loginWithGoogle,
        logout,
        checkSession,
        clearAuthError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};
