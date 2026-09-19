import React from 'react';
import { Composer } from './Composer';
import { ModeBar } from './ModeBar';
import { FeatureMode, ModelSpeed, AttachmentFile } from '../types';

interface HomeScreenProps {
  activeMode: FeatureMode;
  onSelectMode: (mode: FeatureMode) => void;
  onSend: (
    text: string,
    attachments: AttachmentFile[],
    speed: ModelSpeed,
    voiceConfig?: { provider: string; voice_id: string; speed?: number }
  ) => void;
  initialPrompt?: string;
}

export const HomeScreen: React.FC<HomeScreenProps> = ({
  activeMode,
  onSelectMode,
  onSend,
  initialPrompt = ''
}) => {
  return (
    <div className="limo-home-screen">
      <div className="home-content-scroller">
        {/* Hero Brand Section */}
        <div className="hero-brand-section">
          <h1 className="hero-logo-title">LIMO</h1>
          <p className="hero-subtitle">
            Conversational workspace for multi-format content transformation
          </p>
        </div>

        {/* Centered 768px Composer */}
        <Composer
          mode={activeMode}
          onClearMode={() => onSelectMode('none')}
          onSend={onSend}
          initialText={initialPrompt}
        />

        {/* 6 Creation Mode Feature Pills */}
        <ModeBar
          activeMode={activeMode}
          onSelectMode={onSelectMode}
        />
      </div>

      <style>{`
        .limo-home-screen {
          flex: 1;
          height: 100%;
          display: flex;
          flex-direction: column;
          overflow-y: auto;
          background-color: var(--bg-canvas);
          position: relative;
        }

        .home-content-scroller {
          width: 100%;
          max-width: var(--composer-max-width);
          margin: auto;
          padding: 32px 20px 48px 20px;
          display: flex;
          flex-direction: column;
          align-items: center;
          transform: translateY(32px); /* positioned in middle, slightly downside from dead center */
        }

        @media (max-height: 650px) {
          .home-content-scroller {
            transform: translateY(0);
          }
        }

        .hero-brand-section {
          text-align: center;
          margin-bottom: 32px;
        }

        .hero-logo-title {
          font-size: 52px;
          font-weight: 800;
          letter-spacing: 0.14em;
          color: var(--text-primary);
          margin-bottom: 8px;
          text-transform: uppercase;
          user-select: none;
        }

        .hero-subtitle {
          font-size: 14px;
          color: var(--text-muted);
          letter-spacing: 0.02em;
          max-width: 460px;
          line-height: 1.5;
        }
      `}</style>
    </div>
  );
};
