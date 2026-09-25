import React, { useEffect, useState } from 'react';
import { X, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { LimoNavbarLogo } from './LimoNavbarLogo';
import { InteractiveLimoMascot } from './InteractiveLimoMascot';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
  const { loginWithGoogle, authError, clearAuthError } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Close on Escape key press
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleContinueWithGoogle = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await loginWithGoogle();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="limo-login-overlay" onClick={handleBackdropClick} role="dialog" aria-modal="true">
      <div className="limo-login-card animate-scale-up" onClick={(e) => e.stopPropagation()}>
        {/* Close Button in top right */}
        <button
          className="login-close-btn"
          onClick={onClose}
          aria-label="Close modal"
          title="Close (Esc)"
        >
          <X size={18} />
        </button>

        {/* LEFT VISUAL PANEL (Interactive big Limo mascot with cursor reactions) */}
        <div className="login-visual-panel">
          <div className="visual-graphic-container">
            <InteractiveLimoMascot size={180} />
          </div>

          <div className="visual-panel-footer">
            <span className="visual-badge">LIMO PLATFORM</span>
            <p className="visual-subtext">Unified Multimodal Intelligence</p>
          </div>
        </div>

        {/* RIGHT LOGIN PANEL (Strictly single Google action) */}
        <div className="login-action-panel">
          <div className="login-content-box">
            {/* Brand Header */}
            <div className="login-brand-header">
              <div className="brand-icon-wrapper">
                <LimoNavbarLogo size={36} />
              </div>
              <span className="login-brand-wordmark">LIMO</span>
            </div>

            {/* Title & Subtitle */}
            <h2 className="login-title">Welcome to Limo</h2>
            <p className="login-subtitle">Sign in to continue</p>

            {/* Error Notification Card if Auth Failed */}
            {authError && (
              <div className="login-error-card animate-shake">
                <div className="error-icon">⚠️</div>
                <div className="error-text-content">
                  <span className="error-title">Sign-in Issue</span>
                  <p className="error-desc">{authError}</p>
                </div>
                <button
                  type="button"
                  className="error-dismiss-btn"
                  onClick={clearAuthError}
                  title="Dismiss"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Single Google Authentication Action */}
            <div className="login-buttons-group">
              <button
                type="button"
                className="google-auth-button"
                onClick={handleContinueWithGoogle}
                disabled={isSubmitting}
                aria-label="Continue with Google"
              >
                {isSubmitting ? (
                  <Loader2 size={18} className="auth-spinner" />
                ) : (
                  <svg
                    className="google-g-svg"
                    viewBox="0 0 24 24"
                    width="19"
                    height="19"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                    />
                  </svg>
                )}
                <span>Continue with Google</span>
              </button>
            </div>

            {/* Subdued Terms of Service / Privacy Policy */}
            <p className="login-terms-notice">
              By continuing, you agree to Limo's Terms of Service and Privacy Policy.
            </p>
          </div>
        </div>
      </div>

      <style>{`
        .limo-login-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.72);
          backdrop-filter: blur(5px);
          -webkit-backdrop-filter: blur(5px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
          animation: overlayFadeIn 0.2s ease-out;
        }

        .limo-login-card {
          position: relative;
          width: 740px;
          max-width: 95vw;
          height: 480px;
          max-height: 90vh;
          background: var(--bg-card, #131418);
          border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.1));
          border-radius: 20px;
          display: grid;
          grid-template-columns: 1fr 1fr;
          overflow: hidden;
          box-shadow: 0 32px 80px -16px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.06);
          animation: cardPop 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .login-close-btn {
          position: absolute;
          top: 16px;
          right: 16px;
          background: transparent;
          border: none;
          color: var(--text-muted, #71717a);
          width: 32px;
          height: 32px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.15s ease;
          z-index: 10;
        }

        .login-close-btn:hover {
          color: var(--text-primary, #ffffff);
          background: rgba(255, 255, 255, 0.08);
        }

        /* Left Panel */
        .login-visual-panel {
          background: #090a0d;
          border-right: 1px solid rgba(255, 255, 255, 0.06);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 28px;
          position: relative;
          overflow: hidden;
          user-select: none;
        }

        .visual-graphic-container {
          position: relative;
          width: 100%;
          min-height: 280px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .visual-panel-footer {
          margin-top: 12px;
          text-align: center;
          z-index: 2;
        }

        .visual-badge {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.16em;
          color: #3b82f6;
          text-transform: uppercase;
        }

        .visual-subtext {
          font-size: 12px;
          color: var(--text-muted, #71717a);
          margin-top: 4px;
          letter-spacing: 0.02em;
        }

        /* Right Panel */
        .login-action-panel {
          background: var(--bg-card, #131418);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 40px 36px;
        }

        .login-content-box {
          width: 100%;
          max-width: 280px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
        }

        .login-brand-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 24px;
        }

        .brand-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .login-brand-wordmark {
          font-size: 20px;
          font-weight: 800;
          letter-spacing: 0.12em;
          color: var(--text-primary, #ffffff);
        }

        .login-title {
          font-size: 22px;
          font-weight: 700;
          color: var(--text-primary, #ffffff);
          margin: 0;
          letter-spacing: -0.01em;
        }

        .login-subtitle {
          font-size: 13px;
          color: var(--text-muted, #a1a1aa);
          margin: 6px 0 28px 0;
        }

        .login-error-card {
          width: 100%;
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.35);
          border-radius: 10px;
          padding: 10px 12px;
          margin-bottom: 16px;
          display: flex;
          align-items: flex-start;
          gap: 8px;
          text-align: left;
        }

        .error-icon {
          font-size: 14px;
          line-height: 1;
          margin-top: 1px;
        }

        .error-text-content {
          flex: 1;
        }

        .error-title {
          font-size: 11px;
          font-weight: 700;
          color: #f87171;
          display: block;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .error-desc {
          font-size: 11px;
          color: #fca5a5;
          margin: 2px 0 0 0;
          line-height: 1.4;
          word-break: break-word;
        }

        .error-dismiss-btn {
          background: transparent;
          border: none;
          color: #f87171;
          cursor: pointer;
          font-size: 12px;
          padding: 2px 4px;
          border-radius: 4px;
          opacity: 0.8;
          transition: opacity 0.15s ease;
        }

        .error-dismiss-btn:hover {
          opacity: 1;
          background: rgba(239, 68, 68, 0.2);
        }

        .login-buttons-group {
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .google-auth-button {
          width: 100%;
          height: 44px;
          background: var(--bg-pill, #1f2025);
          border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.12));
          border-radius: 10px;
          color: var(--text-primary, #ffffff);
          font-size: 13px;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          cursor: pointer;
          transition: all 0.16s ease;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
          user-select: none;
        }

        .google-auth-button:hover:not(:disabled) {
          background: var(--bg-pill-hover, #272930);
          border-color: rgba(255, 255, 255, 0.24);
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }

        .google-auth-button:active:not(:disabled) {
          transform: translateY(0);
        }

        .google-auth-button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .google-g-svg {
          flex-shrink: 0;
        }

        .auth-spinner {
          animation: spin 1s linear infinite;
          color: #3b82f6;
        }

        .login-terms-notice {
          font-size: 11px;
          line-height: 1.5;
          color: var(--text-placeholder, #52525b);
          margin-top: 26px;
          margin-bottom: 0;
          user-select: none;
        }

        @keyframes overlayFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes cardPop {
          from {
            opacity: 0;
            transform: scale(0.96) translateY(6px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        /* Responsive breakpoints */
        @media (max-width: 680px) {
          .limo-login-card {
            grid-template-columns: 1fr;
            height: auto;
            max-width: 380px;
            padding: 10px 0;
          }

          .login-visual-panel {
            display: none;
          }

          .login-action-panel {
            padding: 36px 24px;
          }
        }
      `}</style>
    </div>
  );
};
