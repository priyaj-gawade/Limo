import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { LimoMascot, MascotEmotion } from './LimoMascot';

export type FeatureInfoType = 'office' | 'code' | 'website';

interface FeatureInfoModalProps {
  isOpen: boolean;
  type: FeatureInfoType | null;
  onClose: () => void;
}

interface FeatureConfig {
  primaryMessage: string;
  supportingText?: string;
  mascotEmotion: MascotEmotion;
  cta: {
    label: string;
    url: string;
  };
}

const FEATURE_CONFIGS: Record<FeatureInfoType, FeatureConfig> = {
  office: {
    primaryMessage: 'Office features are available in the Limo desktop app.',
    supportingText: 'Documents, spreadsheets, and presentations run locally.',
    mascotEmotion: 'happy',
    cta: {
      label: 'Try on',
      url: 'https://github.com/priyaj-gawade/Limo',
    },
  },
  code: {
    primaryMessage: 'Code features are currently under development.',
    mascotEmotion: 'thinking',
    cta: {
      label: 'Visit us',
      url: 'https://github.com/priyaj-gawade/Limo',
    },
  },
  website: {
    primaryMessage: 'Website features are currently under development.',
    mascotEmotion: 'surprised',
    cta: {
      label: 'Visit us',
      url: 'https://github.com/priyaj-gawade/Limo',
    },
  },
};

export const FeatureInfoModal: React.FC<FeatureInfoModalProps> = ({ isOpen, type, onClose }) => {
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

  if (!isOpen || !type) return null;

  const config = FEATURE_CONFIGS[type];
  if (!config) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="limo-feature-modal-overlay"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="feature-info-message"
    >
      <div className="limo-feature-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Independent Close Button top-right (Symmetry & Order) */}
        <button
          className="feature-modal-close-btn"
          onClick={onClose}
          aria-label="Close modal"
          title="Close (Esc)"
        >
          <X size={17} />
        </button>

        {/* Gestalt Conversational Unit: Mascot ──> Speech Bubble ──> CTA */}
        <div className="gestalt-conversation-group">
          {/* 1. LIMO MASCOT: Identity Anchor (brand-cyan #17b8e7 unchanged) */}
          <div className="mascot-stage-wrapper">
            <div className="mascot-slime-bounce">
              <LimoMascot size={190} emotion={config.mascotEmotion} interactive={true} />
            </div>
            <div className="mascot-ground-shadow" />
          </div>

          {/* 2. SPEECH & ACTION CLUSTER: Derived cyan-tinted bubble + proximately grouped CTA */}
          <div className="message-action-cluster">
            {/* The Speech Bubble: Adaptive sizing, calm tint, organic silhouette */}
            <div className={`speech-bubble-body bubble-type-${type}`}>
              {/* Organic speech tail pointing toward mascot */}
              <svg
                className="speech-tail-svg"
                viewBox="0 0 24 34"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                {/* Solid fill matching the tinted bubble */}
                <path
                  d="M24 0 C16 6, 2 12, 0 17 C2 22, 16 28, 24 34 Z"
                  fill="var(--limo-popup-bubble-bg)"
                />
                {/* Seamless outer border contour */}
                <path
                  d="M24 0 C16 6, 2 12, 0 17 C2 22, 16 28, 24 34"
                  fill="none"
                  stroke="var(--limo-popup-bubble-border)"
                  strokeWidth="1"
                />
              </svg>

              {/* Primary Message */}
              <h3 id="feature-info-message" className="bubble-text-primary">
                {config.primaryMessage}
              </h3>

              {/* Supporting Text (Office only) */}
              {config.supportingText && (
                <p className="bubble-text-supporting">{config.supportingText}</p>
              )}
            </div>

            {/* 3. OPTIONAL ACTION: Grouped 14px below bubble, right-aligned */}
            <div className="bubble-action-row">
              <a
                href={config.cta.url}
                target="_blank"
                rel="noopener noreferrer"
                className="feature-action-pill"
                title={`${config.cta.label} on GitHub`}
              >
                <svg
                  className="pill-github-icon"
                  viewBox="0 0 24 24"
                  width="13"
                  height="13"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
                <span className="pill-text">{config.cta.label}</span>
              </a>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        /* -------------------------------------------------------------
           COLOR SYSTEM: Derived tints/shades from Limo cyan (#17b8e7)
           ------------------------------------------------------------- */
        :root {
          /* Dark Mode Defaults */
          --limo-popup-card-bg: #14161b;
          --limo-popup-card-border: rgba(255, 255, 255, 0.08);
          --limo-popup-card-shadow: 0 24px 60px -12px rgba(0, 0, 0, 0.72), 0 0 0 1px rgba(255, 255, 255, 0.03);
          
          /* Dark theme: dark/medium cyan-tinted slate (calm, cohesive) */
          --limo-popup-bubble-bg: #12242f;
          --limo-popup-bubble-border: rgba(23, 184, 231, 0.22);
          --limo-popup-bubble-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
          --limo-popup-text-primary: #f2f6fa;
          --limo-popup-text-supporting: #91a5b4;
          
          /* Dark theme: light CTA pill */
          --limo-popup-cta-bg: #ffffff;
          --limo-popup-cta-text: #090e13;
          --limo-popup-cta-border: #ffffff;
          --limo-popup-cta-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
          
          --limo-popup-close-color: #71717a;
          --limo-popup-close-hover: #ffffff;
          --limo-popup-close-hover-bg: rgba(255, 255, 255, 0.08);
        }

        [data-theme="light"] {
          /* Light Mode Overrides */
          --limo-popup-card-bg: #ffffff;
          --limo-popup-card-border: rgba(0, 0, 0, 0.08);
          --limo-popup-card-shadow: 0 20px 48px -10px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.03);
          
          /* Light theme: very light cyan-tinted bubble (subtle, airy) */
          --limo-popup-bubble-bg: #edf7fa;
          --limo-popup-bubble-border: rgba(23, 184, 231, 0.22);
          --limo-popup-bubble-shadow: 0 2px 10px rgba(12, 38, 52, 0.05);
          --limo-popup-text-primary: #090e13;
          --limo-popup-text-supporting: #465866;
          
          /* Light theme: dark CTA pill */
          --limo-popup-cta-bg: #090e13;
          --limo-popup-cta-text: #ffffff;
          --limo-popup-cta-border: #090e13;
          --limo-popup-cta-shadow: 0 2px 8px rgba(0, 0, 0, 0.14);
          
          --limo-popup-close-color: #71717a;
          --limo-popup-close-hover: #090e13;
          --limo-popup-close-hover-bg: rgba(0, 0, 0, 0.06);
        }

        /* -------------------------------------------------------------
           FIGURE-GROUND: Restrained, resolved modal container
           ------------------------------------------------------------- */
        .limo-feature-modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.65);
          backdrop-filter: blur(5px);
          -webkit-backdrop-filter: blur(5px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 24px;
          animation: modalOverlayFade 0.18s ease-out;
        }

        @keyframes modalOverlayFade {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        /* Sized comfortably with ~10% height reduction for a resolved frame */
        .limo-feature-modal-card {
          position: relative;
          width: 580px;
          max-width: 92vw;
          background: var(--limo-popup-card-bg);
          border: 1px solid var(--limo-popup-card-border);
          border-radius: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 34px 36px 30px 32px;
          box-shadow: var(--limo-popup-card-shadow);
          animation: modalContentSettle 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes modalContentSettle {
          from {
            opacity: 0;
            transform: scale(0.97) translateY(4px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }

        /* Independent Close Button (Symmetry & Order) */
        .feature-modal-close-btn {
          position: absolute;
          top: 15px;
          right: 15px;
          background: transparent;
          border: none;
          color: var(--limo-popup-close-color);
          width: 28px;
          height: 28px;
          border-radius: 7px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.15s ease;
          z-index: 10;
        }

        .feature-modal-close-btn:hover {
          color: var(--limo-popup-close-hover);
          background: var(--limo-popup-close-hover-bg);
        }

        /* -------------------------------------------------------------
           PROXIMITY & CONTINUITY: Unified Conversational Unit
           Mascot ──> Speech Bubble ──> CTA
           ------------------------------------------------------------- */
        .gestalt-conversation-group {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 14px;
          width: 100%;
        }

        /* 1. Mascot Stage: Character identity anchor */
        .mascot-stage-wrapper {
          position: relative;
          flex-shrink: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 190px;
          user-select: none;
        }

        /* Common Fate: Occasional natural slime bounce (mascot only) */
        .mascot-slime-bounce {
          position: relative;
          z-index: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          transform-origin: center bottom;
          animation: slimeOrganicBounce 7.5s cubic-bezier(0.45, 0, 0.55, 1) infinite;
        }

        @keyframes slimeOrganicBounce {
          0%, 18%, 100% {
            transform: translateY(0) scale(1, 1);
          }
          3% {
            transform: translateY(3px) scale(1.04, 0.96);
          }
          8% {
            transform: translateY(-12px) scale(0.96, 1.04);
          }
          12% {
            transform: translateY(-2px) scale(0.99, 1.01);
          }
          15% {
            transform: translateY(1px) scale(1.01, 0.99);
          }
          17% {
            transform: translateY(0) scale(1, 1);
          }
        }

        .mascot-ground-shadow {
          width: 95px;
          height: 9px;
          border-radius: 50%;
          background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0.30) 0%, rgba(0, 0, 0, 0.06) 60%, transparent 75%);
          filter: blur(4px);
          margin-top: 3px;
        }

        [data-theme="light"] .mascot-ground-shadow {
          background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0.14) 0%, rgba(0, 0, 0, 0.02) 60%, transparent 75%);
        }

        /* 2. Message + Action Cluster */
        .message-action-cluster {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          flex: 1;
        }

        /* Speech Bubble: Adaptive sizing, organic silhouette, calm cyan tint */
        .speech-bubble-body {
          position: relative;
          background: var(--limo-popup-bubble-bg);
          border: 1px solid var(--limo-popup-bubble-border);
          border-radius: 18px;
          padding: 18px 22px;
          box-sizing: border-box;
          box-shadow: var(--limo-popup-bubble-shadow);
        }

        /* Adaptive bubble widths tailored to message content */
        .speech-bubble-body.bubble-type-office {
          max-width: 330px;
          width: 100%;
        }

        .speech-bubble-body.bubble-type-code,
        .speech-bubble-body.bubble-type-website {
          max-width: 300px;
          width: 100%;
          padding: 16px 20px;
        }

        /* Speech tail: Organic contour pointing directly toward mascot */
        .speech-tail-svg {
          position: absolute;
          left: -19px;
          top: 50%;
          transform: translateY(-50%);
          width: 20px;
          height: 34px;
          pointer-events: none;
          z-index: 2;
        }

        .bubble-text-primary {
          font-size: 16.5px;
          font-weight: 650;
          line-height: 1.38;
          color: var(--limo-popup-text-primary);
          margin: 0;
          letter-spacing: -0.015em;
        }

        .bubble-text-supporting {
          font-size: 13px;
          line-height: 1.45;
          color: var(--limo-popup-text-supporting);
          margin: 8px 0 0 0;
          font-weight: 500;
          letter-spacing: -0.005em;
        }

        /* 3. Action Row: Proximately grouped 14px below bubble, right-aligned */
        .bubble-action-row {
          margin-top: 14px;
          display: flex;
          justify-content: flex-end;
          width: 100%;
        }

        .feature-action-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: var(--limo-popup-cta-bg);
          color: var(--limo-popup-cta-text);
          border: 1px solid var(--limo-popup-cta-border);
          padding: 6px 13px;
          border-radius: 9999px;
          font-size: 12px;
          font-weight: 600;
          text-decoration: none;
          cursor: pointer;
          transition: all 0.16s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: var(--limo-popup-cta-shadow);
          user-select: none;
        }

        .feature-action-pill:hover {
          transform: translateY(-1px);
          opacity: 0.94;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.20);
        }

        .pill-github-icon {
          flex-shrink: 0;
        }

        .pill-text {
          letter-spacing: 0.01em;
        }

        /* Accessibility: Prefers reduced motion */
        @media (prefers-reduced-motion: reduce) {
          .mascot-slime-bounce,
          .limo-feature-modal-card,
          .limo-feature-modal-overlay {
            animation: none !important;
            transform: none !important;
          }
        }

        /* Responsive Breakpoint for mobile screens */
        @media (max-width: 600px) {
          .limo-feature-modal-card {
            padding: 30px 18px 22px 18px;
          }

          .gestalt-conversation-group {
            flex-direction: column;
            gap: 16px;
          }

          .mascot-stage-wrapper {
            width: 150px;
          }

          .message-action-cluster {
            max-width: 100%;
            align-items: center;
          }

          .speech-tail-svg {
            display: none;
          }

          .bubble-text-primary {
            font-size: 15.5px;
            text-align: center;
          }

          .bubble-text-supporting {
            font-size: 12.5px;
            text-align: center;
          }

          .bubble-action-row {
            justify-content: center;
          }
        }
      `}</style>
    </div>
  );
};
