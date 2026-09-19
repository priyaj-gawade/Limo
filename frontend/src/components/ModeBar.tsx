import React from 'react';
import {
  FileText,
  Presentation,
  Table,
  Video,
  Volume2,
  Globe,
  Code2
} from 'lucide-react';
import { FeatureMode } from '../types';

interface ModeBarProps {
  activeMode: FeatureMode;
  onSelectMode: (mode: FeatureMode) => void;
}

export const ModeBar: React.FC<ModeBarProps> = ({ activeMode, onSelectMode }) => {
  const modes: { id: FeatureMode; label: string; icon: React.ReactNode }[] = [
    { id: 'docs', label: 'Docs', icon: <FileText size={14} /> },
    { id: 'slides', label: 'Slides', icon: <Presentation size={14} /> },
    { id: 'sheets', label: 'Sheets', icon: <Table size={14} /> },
    { id: 'video', label: 'Video', icon: <Video size={14} /> },
    { id: 'audio', label: 'Audio', icon: <Volume2 size={14} /> },
    { id: 'websites', label: 'Websites', icon: <Globe size={14} /> },
    { id: 'code', label: 'Code', icon: <Code2 size={14} /> },
  ];

  return (
    <div className="limo-mode-bar">
      <div className="mode-pills-row">
        {modes.map((m) => {
          const isSelected = activeMode === m.id;
          return (
            <button
              key={m.id}
              className={`mode-feature-pill ${isSelected ? 'active' : ''}`}
              onClick={() => onSelectMode(isSelected ? 'none' : m.id)}
              title={`Switch to ${m.label} creation mode`}
            >
              <span className="pill-icon">{m.icon}</span>
              <span className="pill-text">{m.label}</span>
            </button>
          );
        })}
      </div>

      <style>{`
        .limo-mode-bar {
          width: 100%;
          max-width: var(--composer-max-width);
          margin: 16px auto 0 auto;
          display: flex;
          justify-content: center;
        }

        .mode-pills-row {
          display: flex;
          align-items: center;
          justify-content: center;
          flex-wrap: wrap;
          gap: 10px;
        }

        .mode-feature-pill {
          display: flex;
          align-items: center;
          gap: 7px;
          background: var(--bg-pill);
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 7px 15px;
          border-radius: var(--radius-pill);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          user-select: none;
        }

        .mode-feature-pill:hover {
          background: var(--bg-pill-hover);
          border-color: var(--border-focus);
          color: var(--text-primary);
          transform: translateY(-1px);
        }

        .mode-feature-pill.active {
          background: var(--bg-pill-active);
          border-color: var(--border-active);
          color: var(--text-primary);
          box-shadow: var(--shadow-card);
          font-weight: 600;
        }

        .pill-icon {
          display: flex;
          align-items: center;
          color: var(--text-muted);
          transition: color 0.15s ease;
        }

        .mode-feature-pill:hover .pill-icon,
        .mode-feature-pill.active .pill-icon {
          color: var(--text-primary);
        }

        .pill-text {
          white-space: nowrap;
        }
      `}</style>
    </div>
  );
};
