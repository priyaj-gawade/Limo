import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Brain,
  CheckCircle2,
  Sparkles,
  FileText,
  Presentation,
  Table,
  Video,
  Globe,
  Paperclip,
  Share2,
  Code2,
  Download,
  ExternalLink,
  Copy,
  RotateCcw,
  Volume2
} from 'lucide-react';
import { Composer } from './Composer';
import { VideoPlayerCard } from './VideoPlayerCard';
import { ChatSession, Artifact, FeatureMode, ModelSpeed, AttachmentFile } from '../types';

interface ChatViewProps {
  session: ChatSession;
  activeMode: FeatureMode;
  onSelectMode: (mode: FeatureMode) => void;
  onSend: (
    text: string,
    attachments: AttachmentFile[],
    speed: ModelSpeed,
    voiceConfig?: { provider: string; voice_id: string; speed?: number }
  ) => void;
  isGenerating: boolean;
  onOpenInWorkspace: (artifact: Artifact) => void;
  onDownloadArtifact?: (artifact: Artifact) => void;
}

export const ChatView: React.FC<ChatViewProps> = ({
  session,
  activeMode,
  onSelectMode,
  onSend,
  isGenerating,
  onOpenInWorkspace,
  onDownloadArtifact
}) => {
  const [expandedThinking, setExpandedThinking] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const toggleThinking = (msgId: string) => {
    setExpandedThinking((prev) => ({
      ...prev,
      [msgId]: !prev[msgId]
    }));
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session.messages, isGenerating]);

  const getArtifactIcon = (type: Artifact['type']) => {
    switch (type) {
      case 'doc':
        return <FileText size={18} className="artifact-icon-doc" />;
      case 'slide':
        return <Presentation size={18} className="artifact-icon-slide" />;
      case 'sheet':
        return <Table size={18} className="artifact-icon-sheet" />;
      case 'video':
        return <Video size={18} className="artifact-icon-video" />;
      case 'audio':
        return <Volume2 size={18} className="artifact-icon-audio" />;
      case 'website':
        return <Globe size={18} className="artifact-icon-website" />;
      case 'code':
        return <Code2 size={18} className="artifact-icon-code" />;
      default:
        return <FileText size={18} />;
    }
  };

  const formatArtifactSize = (bytes?: number): string => {
    if (!bytes || bytes <= 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatBadge = (art: Artifact): string => {
    const ext = (art.fileFormat || '').toUpperCase().replace(/^\./, '');
    const size = formatArtifactSize(art.sizeBytes);
    return size ? `${ext} • ${size}` : ext;
  };

  return (
    <div className="limo-chat-view">
      {/* Top Session Header */}
      <div className="chat-session-header">
        <div className="session-title-wrap">
          <h2 className="session-title">{session.title}</h2>
          {session.mode !== 'none' && (
            <span className="session-mode-badge">{session.mode.toUpperCase()}</span>
          )}
        </div>
        <div className="session-header-actions">
          <button className="header-action-btn" onClick={() => alert('Chat link copied')}>
            <Share2 size={14} />
            <span>Share</span>
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="chat-messages-container">
        <div className="messages-inner-width">
          {session.messages.map((message) => {
            const isUser = message.role === 'user';
            const isThinkingOpen = expandedThinking[message.id] ?? false;

            return (
              <div key={message.id} className={`message-row ${isUser ? 'user-turn' : 'assistant-turn'}`}>
                {/* Turn Header / Identity */}
                <div className="message-header">
                  <div className="author-badge">
                    {isUser ? (
                      <div className="avatar user-avatar">P</div>
                    ) : (
                      <div className="avatar limo-avatar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path d="M4 4v16h16" />
                          <polyline points="4 12 12 12 20 4" />
                        </svg>
                      </div>
                    )}
                    <span className="author-name">{isUser ? 'You' : 'Limo'}</span>
                  </div>
                </div>

                {/* Message Body */}
                <div className="message-body">
                  {/* User Attachments (if any) */}
                  {isUser && message.attachments && message.attachments.length > 0 && (
                    <div className="user-attachments-grid">
                      {message.attachments.map((att) => (
                        <div key={att.id} className="user-attachment-pill">
                          <Paperclip size={13} />
                          <span className="user-attachment-name">{att.name}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Assistant Thinking Step Timeline */}
                  {!isUser && message.thinkingSteps && message.thinkingSteps.length > 0 && (
                    <div className="thinking-accordion">
                      <button
                        className="thinking-toggle-btn"
                        onClick={() => toggleThinking(message.id)}
                      >
                        <div className="thinking-toggle-left">
                          <Brain size={15} className="thinking-brain-icon" />
                          <span>Thought for {message.thinkingDurationSec || 2.4}s</span>
                        </div>
                        {isThinkingOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>

                      {isThinkingOpen && (
                        <div className="thinking-timeline-body animate-fade-in">
                          {message.thinkingSteps.map((step, idx) => (
                            <div key={step.id} className="thinking-step-item">
                              <div className="step-indicator">
                                <CheckCircle2 size={13} className="step-check" />
                                {idx < (message.thinkingSteps?.length ?? 0) - 1 && <div className="step-line" />}
                              </div>
                              <div className="step-content">
                                <div className="step-title">{step.title}</div>
                                {step.description && <div className="step-desc">{step.description}</div>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Main Message Text */}
                  <div className="message-content-text">
                    {message.content}
                  </div>

                  {/* Interactive Artifact Cards */}
                  {!isUser && message.artifacts && message.artifacts.length > 0 && (
                    <div className="artifacts-grid">
                      {message.artifacts.map((art) => {
                        if (art.type === 'video') {
                          return (
                            <VideoPlayerCard
                              key={art.id}
                              artifact={art}
                              onDownloadArtifact={onDownloadArtifact}
                            />
                          );
                        }

                        return (
                          <div key={art.id} className="artifact-card">
                            {/* Top Row: Title & Format/Size Badge */}
                            <div className="artifact-header-row">
                              <div className="artifact-header-left">
                                <span className="artifact-icon-mini">{getArtifactIcon(art.type)}</span>
                                <h4 className="artifact-title" title={art.title}>{art.title}</h4>
                              </div>
                              <span className="format-badge">{formatBadge(art)}</span>
                            </div>

                            {/* Middle Row: Safe Subagent Summary */}
                            {(message.executionSummary || art.description) && (
                              <p className="artifact-subagent-summary">
                                {message.executionSummary || art.description}
                              </p>
                            )}

                            {/* Bottom Row: [ Audio Player ] or [ Edit + THUMBNAIL ] */}
                            {art.type === 'audio' ? (
                              <div className="audio-artifact-player-row">
                                <audio
                                  controls
                                  src={`/api/v1/artifacts/${art.id}/download`}
                                  className="limo-audio-player"
                                  preload="metadata"
                                />
                                <button
                                  className="artifact-download-pill"
                                  onClick={() => onDownloadArtifact && onDownloadArtifact(art)}
                                  title="Download MP3"
                                >
                                  <Download size={13} />
                                  <span>Download</span>
                                </button>
                              </div>
                            ) : (
                              <div className="artifact-action-row">
                                <button
                                  className="artifact-edit-pill"
                                  onClick={() => onOpenInWorkspace(art)}
                                  title="Open document in GenOffice workspace"
                                >
                                  Edit
                                </button>

                                <div
                                  className="artifact-thumbnail-container"
                                  onClick={() => onDownloadArtifact && onDownloadArtifact(art)}
                                  title="Click to download document"
                                >
                                  <img
                                    src={art.thumbnailUrl || `/api/v1/artifacts/${art.id}/thumbnail`}
                                    alt={art.title}
                                    className="artifact-thumbnail-img"
                                    onError={(e) => {
                                      (e.currentTarget as HTMLElement).style.display = 'none';
                                      const fallback = (e.currentTarget.parentElement?.querySelector(
                                        '.artifact-thumbnail-fallback'
                                      ) as HTMLElement | null);
                                      if (fallback) fallback.style.display = 'flex';
                                    }}
                                  />
                                  <div className="artifact-thumbnail-fallback" style={{ display: 'none' }}>
                                    {getArtifactIcon(art.type)}
                                    <span className="fallback-ext">{(art.fileFormat || '').toUpperCase().replace(/^\./, '')}</span>
                                  </div>
                                  <div className="artifact-thumbnail-overlay">
                                    <div className="thumbnail-download-circle">
                                      <Download size={18} />
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Message Actions */}
                  {!isUser && (
                    <div className="message-actions-row">
                      <button
                        className="msg-action-btn"
                        onClick={() => {
                          navigator.clipboard.writeText(message.content);
                          alert('Copied to clipboard');
                        }}
                        title="Copy message"
                      >
                        <Copy size={13} />
                      </button>
                      <button
                        className="msg-action-btn"
                        onClick={() => alert('Regenerate turn')}
                        title="Regenerate"
                      >
                        <RotateCcw size={13} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Real State Loading Indicator (active during isGenerating) */}
          {isGenerating && (
            <div className="message-row assistant-turn animate-fade-in">
              <div className="message-header">
                <div className="author-badge">
                  <div className="avatar limo-avatar animate-pulse-subtle">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M4 4v16h16" />
                      <polyline points="4 12 12 12 20 4" />
                    </svg>
                  </div>
                  <span className="author-name">Limo</span>
                </div>
              </div>
              <div className="message-body">
                <div className="generating-indicator">
                  <Sparkles size={16} className="generating-sparkle" />
                  <span>Processing prompt...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Sticky Bottom Composer */}
      <div className="chat-bottom-composer-wrap">
        <Composer
          mode={activeMode}
          onClearMode={() => onSelectMode('none')}
          onSend={onSend}
          disabled={isGenerating}
        />
      </div>

      <style>{`
        .limo-chat-view {
          flex: 1;
          height: 100%;
          display: flex;
          flex-direction: column;
          background-color: var(--bg-canvas);
          overflow: hidden;
          position: relative;
        }

        .chat-session-header {
          height: 48px;
          border-bottom: 1px solid var(--border-subtle);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 24px;
          flex-shrink: 0;
          background: #191918;
        }

        .session-title-wrap {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .session-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          max-width: 400px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .session-mode-badge {
          font-size: 10px;
          font-weight: 600;
          background: rgba(255, 255, 255, 0.1);
          color: #ffffff;
          padding: 2px 7px;
          border-radius: 9999px;
        }

        .header-action-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          background: transparent;
          border: 1px solid var(--border-subtle);
          color: var(--text-secondary);
          font-size: 12px;
          padding: 4px 10px;
          border-radius: var(--radius-sm);
          cursor: pointer;
        }

        .header-action-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        .chat-messages-container {
          flex: 1;
          overflow-y: auto;
          padding: 28px 24px 20px 24px;
          display: flex;
          flex-direction: column;
        }

        .messages-inner-width {
          width: 100%;
          max-width: var(--composer-max-width);
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 28px;
        }

        .message-row {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .message-header {
          display: flex;
          align-items: center;
        }

        .author-badge {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .avatar {
          width: 24px;
          height: 24px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          font-weight: 600;
        }

        .user-avatar {
          background: #334155;
          color: #ffffff;
        }

        .limo-avatar {
          background: #ffffff;
          color: #141413;
        }

        .author-name {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .message-body {
          padding-left: 32px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .user-attachments-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .user-attachment-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(255, 255, 255, 0.07);
          border: 1px solid var(--border-subtle);
          padding: 4px 10px;
          border-radius: var(--radius-md);
          font-size: 12px;
          color: var(--text-secondary);
        }

        .user-turn .message-content-text {
          color: #ffffff;
          font-size: 15px;
          line-height: 1.6;
        }

        .assistant-turn .message-content-text {
          color: var(--text-primary);
          font-size: 14.5px;
          line-height: 1.65;
          white-space: pre-wrap;
        }

        .thinking-accordion {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
          overflow: hidden;
        }

        .thinking-toggle-btn {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 12px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          font-size: 12px;
          cursor: pointer;
        }

        .thinking-toggle-btn:hover {
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.03);
        }

        .thinking-toggle-left {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .thinking-brain-icon {
          color: #60a5fa;
        }

        .thinking-timeline-body {
          padding: 12px 14px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .thinking-step-item {
          display: flex;
          gap: 12px;
          position: relative;
        }

        .step-indicator {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 16px;
        }

        .step-check {
          color: #4ade80;
        }

        .step-line {
          width: 1px;
          flex: 1;
          background: rgba(255, 255, 255, 0.1);
          margin-top: 4px;
          min-height: 16px;
        }

        .step-content {
          flex: 1;
        }

        .step-title {
          font-size: 12.5px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .step-desc {
          font-size: 11.5px;
          color: var(--text-muted);
          margin-top: 2px;
        }

        .artifacts-grid {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-top: 10px;
        }

        .artifact-card {
          background: #1f1f1e;
          border: 1px solid var(--border-medium);
          border-radius: var(--radius-card);
          padding: 16px 18px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-width: 520px;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .artifact-card:hover {
          border-color: rgba(255, 255, 255, 0.2);
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }

        .artifact-header-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }

        .artifact-header-left {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow: hidden;
        }

        .artifact-icon-mini {
          display: flex;
          align-items: center;
          flex-shrink: 0;
        }

        .artifact-icon-doc { color: #60a5fa; }
        .artifact-icon-slide { color: #facc15; }
        .artifact-icon-sheet { color: #4ade80; }
        .artifact-icon-video { color: #c084fc; }
        .artifact-icon-audio { color: #f59e0b; }
        .artifact-icon-website { color: #38bdf8; }
        .artifact-icon-code { color: #fb923c; }

        .audio-artifact-player-row {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-top: 10px;
          width: 100%;
        }

        .limo-audio-player {
          flex: 1;
          height: 36px;
          border-radius: var(--radius-pill);
          outline: none;
        }

        .artifact-download-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: var(--radius-pill);
          color: var(--text-primary);
          font-size: 12px;
          font-weight: 500;
          padding: 6px 12px;
          cursor: pointer;
          transition: all 0.14s ease;
          white-space: nowrap;
        }

        .artifact-download-pill:hover {
          background: rgba(255, 255, 255, 0.15);
          border-color: rgba(255, 255, 255, 0.25);
        }

        .artifact-title {
          font-size: 14px;
          font-weight: 600;
          color: #ffffff;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .format-badge {
          font-size: 11px;
          font-weight: 600;
          background: rgba(255, 255, 255, 0.08);
          color: #cbd5e1;
          padding: 2px 8px;
          border-radius: 4px;
          white-space: nowrap;
          flex-shrink: 0;
          letter-spacing: 0.3px;
        }

        .artifact-subagent-summary {
          font-size: 12.5px;
          line-height: 1.5;
          color: #a1a1aa;
          margin: 0;
        }

        .artifact-action-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-top: 2px;
        }

        .artifact-edit-pill {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 7px 24px;
          border-radius: 9999px;
          font-size: 13px;
          font-weight: 600;
          color: #141413;
          background: #f4f4f3;
          border: 1px solid #e2e2e0;
          cursor: pointer;
          transition: all 0.15s ease;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
        }

        .artifact-edit-pill:hover {
          background: #ffffff;
          border-color: #ffffff;
          transform: translateY(-1px);
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
        }

        .artifact-edit-pill:active {
          transform: translateY(0);
        }

        .artifact-thumbnail-container {
          position: relative;
          width: 190px;
          height: 118px;
          border-radius: 8px;
          overflow: hidden;
          background: #141413;
          border: 1px solid rgba(255, 255, 255, 0.12);
          cursor: pointer;
          flex-shrink: 0;
        }

        .artifact-thumbnail-img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
          transition: filter 0.25s ease, transform 0.25s ease;
        }

        .artifact-thumbnail-container:hover .artifact-thumbnail-img {
          filter: blur(4px) brightness(0.65);
          transform: scale(1.03);
        }

        .artifact-thumbnail-fallback {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          background: #1b1b1a;
          color: #94a3b8;
        }

        .fallback-ext {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.5px;
          color: #64748b;
        }

        .artifact-thumbnail-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0, 0, 0, 0.25);
          opacity: 0;
          transition: opacity 0.2s ease;
          pointer-events: none;
        }

        .artifact-thumbnail-container:hover .artifact-thumbnail-overlay {
          opacity: 1;
        }

        .thumbnail-download-circle {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: #141413;
          border: 1px solid rgba(255, 255, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          color: #ffffff;
          box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5);
          transition: transform 0.15s ease;
        }

        .artifact-thumbnail-container:hover .thumbnail-download-circle {
          transform: scale(1.06);
        }

        .message-actions-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 4px;
        }

        .msg-action-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 4px;
          border-radius: 4px;
        }

        .msg-action-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.06);
        }

        .generating-indicator {
          display: flex;
          align-items: center;
          gap: 10px;
          color: var(--text-secondary);
          font-size: 13.5px;
        }

        .generating-sparkle {
          color: #60a5fa;
          animation: spin 3s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .chat-bottom-composer-wrap {
          padding: 12px 24px 24px 24px;
          background: linear-gradient(to top, var(--bg-canvas) 85%, transparent 100%);
        }
      `}</style>
    </div>
  );
};
