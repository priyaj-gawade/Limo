import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '../types';
import { useToast } from './ToastContext';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isLoginModalOpen: boolean;
  openLoginModal: () => void;
  closeLoginModal: () => void;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState<boolean>(false);
  const { showToast } = useToast();

  const openLoginModal = useCallback(() => {
    setIsLoginModalOpen(true);
  }, []);

  const closeLoginModal = useCallback(() => {
    setIsLoginModalOpen(false);
  }, []);

  // Check current session from backend
  const checkSession = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/auth/me', {
        credentials: 'include',
      });
      if (res.ok) {
        const data: User = await res.json();
        // A user is fully authenticated if provider === 'google'
        if (data && data.provider === 'google') {
          setUser(data);
          setIsLoginModalOpen(false);
          return;
        }
      }
      setUser(null);
      // Auto-open login modal on first visit or page reload when unauthenticated
      if (window.location.pathname !== '/auth/callback') {
        setIsLoginModalOpen(true);
      }
    } catch (err) {
      console.error('Session check failed:', err);
      setUser(null);
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
                // Post to opener window if this was a popup
                window.opener.postMessage(
                  { type: 'LIMO_AUTH_SUCCESS', user: authedUser },
                  window.location.origin
                );
                window.close();
                return;
              } else {
                setUser(authedUser);
                window.history.replaceState({}, document.title, '/');
                showToast(`Signed in as ${authedUser.display_name || authedUser.email}`, 'success');
              }
            } else {
              const err = await res.json().catch(() => ({}));
              if (window.opener) {
                window.opener.postMessage(
                  { type: 'LIMO_AUTH_ERROR', error: err.detail || 'Authentication failed' },
                  window.location.origin
                );
                window.close();
                return;
              }
              showToast(err.detail || 'Google sign-in failed', 'error');
              window.history.replaceState({}, document.title, '/');
            }
          } catch (err) {
            console.error('Callback error:', err);
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
        setIsLoginModalOpen(false);
        showToast(`Signed in as ${loggedUser.display_name || loggedUser.email}`, 'success');
      } else if (event.data?.type === 'LIMO_AUTH_ERROR') {
        showToast(event.data.error || 'Google authentication failed', 'error');
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
    try {
      const res = await fetch('/api/v1/auth/login', {
        credentials: 'include',
      });
      if (!res.ok) {
        throw new Error('Failed to initialize Google authentication');
      }

      const data = await res.json();
      const authUrl = data.authorization_url;

      if (!authUrl) {
        throw new Error('No authorization URL returned by backend');
      }

      // Open a centered Google OAuth popup
      const width = 500;
      const height = 620;
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

      // Check for popup closed without completion
      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          // Check session once popup closes
          checkSession();
        }
      }, 800);
    } catch (err: any) {
      console.error('Google login error:', err);
      showToast(err.message || 'Could not connect to Google sign-in', 'error');
    }
  };

  const logout = async () => {
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
      setUser(null);
      setIsLoginModalOpen(true);
      showToast('Logged out successfully', 'info');
    } catch (err) {
      console.error('Logout error:', err);
      setUser(null);
      setIsLoginModalOpen(true);
    }
  };

  // True if user is logged in with a real Google account
  const isAuthenticated = Boolean(user && user.provider === 'google');

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        isLoginModalOpen,
        openLoginModal,
        closeLoginModal,
        loginWithGoogle,
        logout,
        checkSession,
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
