import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Brain,
  CheckCircle2,
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
  Volume2,
  Image as ImageIcon
} from 'lucide-react';
import { Composer } from './Composer';
import { VideoPlayerCard } from './VideoPlayerCard';
import { MarkdownMessage } from './MarkdownMessage';
import { useToast } from '../context/ToastContext';
import { ChatSession, Artifact, FeatureMode, ModelSpeed, AttachmentFile } from '../types';
import { getFileCategory, getCategorySubtitle, renderAttachmentBadge } from '../utils/attachmentUtils';
import { LimoMascot } from './LimoMascot';
import { ThinkingTextAnimation } from './ThinkingTextAnimation';
import { LimoAudioPlayer } from './LimoAudioPlayer';

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
  const [hoveredArtifactId, setHoveredArtifactId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { showToast } = useToast();

  const handleRegenerate = (msgId: string) => {
    const msgIndex = session.messages.findIndex((m) => m.id === msgId);
    let userPrompt = '';
    let userAttachments: AttachmentFile[] = [];
    if (msgIndex >= 0) {
      for (let i = msgIndex - 1; i >= 0; i--) {
        if (session.messages[i].role === 'user') {
          userPrompt = session.messages[i].content;
          userAttachments = session.messages[i].attachments || [];
          break;
        }
      }
    }
    if (userPrompt) {
      showToast('Regenerating response...', 'info');
      onSend(userPrompt, userAttachments, 'Instant');
    } else {
      showToast('No previous user prompt to regenerate', 'info');
    }
  };

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
      case 'infographic':
        return <ImageIcon size={18} className="artifact-icon-image" />;
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
          <button
            className="header-action-btn"
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              showToast('Chat link copied to clipboard', 'success');
            }}
          >
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

            if (isUser) {
              const attachments = message.attachments || [];
              const images = attachments.filter((a) => {
                const cat = a.fileCategory || getFileCategory(a.name, a.type);
                return cat === 'image' && (a.previewUrl || a.url);
              });
              const documents = attachments.filter((a) => {
                const cat = a.fileCategory || getFileCategory(a.name, a.type);
                return cat !== 'image' || (!a.previewUrl && !a.url);
              });

              const isFourImagesOnly = images.length === 4 && documents.length === 0;

              return (
                <div key={message.id} className="message-row user-turn">
                  <div className="user-bubble-wrap">
                    {attachments.length > 0 && (
                      <div className="user-attachments-scroll-window slim-scrollbar">
                        {isFourImagesOnly ? (
                          <div className="user-images-2x2-grid">
                            {images.map((img) => (
                              <div key={img.id} className="grid-2x2-item">
                                <img
                                  src={img.previewUrl || img.url}
                                  alt={img.name}
                                  className="grid-img-el"
                                />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <>
                            {images.length > 0 && (
                              <div className={`user-images-flex-grid count-${Math.min(images.length, 4)}`}>
                                {images.map((img) => (
                                  <div key={img.id} className="user-image-bubble-card">
                                    <img
                                      src={img.previewUrl || img.url}
                                      alt={img.name}
                                      className="grid-img-el"
                                    />
                                  </div>
                                ))}
                              </div>
                            )}

                            {documents.map((doc) => {
                              const category = doc.fileCategory || getFileCategory(doc.name, doc.type);
                              return (
                                <div key={doc.id} className="chatgpt-file-card user-chat-file-card">
                                  <div className="file-card-badge-wrap">
                                    {renderAttachmentBadge(category)}
                                  </div>
                                  <div className="file-card-meta">
                                    <div className="file-card-title" title={doc.name}>{doc.name}</div>
                                    <div className="file-card-subtitle">
                                      {getCategorySubtitle(category, doc.name)}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </>
                        )}
                      </div>
                    )}

                    {message.content && (
                      <div className="user-message-bubble">
                        {message.content}
                      </div>
                    )}
                  </div>
                </div>
              );
            }

            return (
              <div key={message.id} className="message-row assistant-turn">
                <div className="limo-mascot-col">
                  <div className="limo-mascot-wrap" title="Limo">
                    <LimoMascot size={42} />
                  </div>
                </div>

                <div className="assistant-content-col">
                  {/* Assistant Thinking Step Timeline */}
                  {message.thinkingSteps && message.thinkingSteps.length > 0 && (
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

                  {/* Main Message Text (Rich Markdown Presentation) */}
                  <div className="message-content-text">
                    <MarkdownMessage content={message.content} />
                  </div>

                  {/* Interactive Artifact Cards */}
                  {message.artifacts && message.artifacts.length > 0 && (
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

                        if (art.type === 'infographic') {
                          const isHovered = hoveredArtifactId === art.id;
                          return (
                            <div
                              key={art.id}
                              className={`clean-image-deliverable ${isHovered ? 'is-hovered' : ''}`}
                              onMouseEnter={() => setHoveredArtifactId(art.id)}
                              onMouseLeave={() => setHoveredArtifactId(null)}
                              onClick={() => onDownloadArtifact && onDownloadArtifact(art)}
                              title="Click to download infographic"
                            >
                              <img
                                src={art.thumbnailUrl || `/api/v1/artifacts/${art.id}/download`}
                                alt={art.title}
                                className="clean-image-img"
                                onError={(e) => {
                                  (e.currentTarget as HTMLElement).style.display = 'none';
                                  const fallback = (e.currentTarget.parentElement?.querySelector(
                                    '.image-artifact-fallback'
                                  ) as HTMLElement | null);
                                  if (fallback) fallback.style.display = 'flex';
                                }}
                              />
                              <div className="image-artifact-fallback" style={{ display: 'none' }}>
                                {getArtifactIcon(art.type)}
                                <span className="fallback-ext">PNG</span>
                              </div>
                              <button
                                className="image-download-btn"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDownloadArtifact && onDownloadArtifact(art);
                                }}
                                title="Download PNG"
                                aria-label="Download image"
                              >
                                <Download size={15} />
                              </button>
                            </div>
                          );
                        }

                        if (art.type === 'audio') {
                          return (
                            <LimoAudioPlayer
                              key={art.id}
                              src={`/api/v1/artifacts/${art.id}/download`}
                              onDownload={() => onDownloadArtifact && onDownloadArtifact(art)}
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

                            {/* Bottom Row: [ Edit + THUMBNAIL ] */}
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
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Message Actions */}
                  <div className="message-actions-row">
                    <button
                      className="msg-action-btn"
                      onClick={() => {
                        navigator.clipboard.writeText(message.content);
                        showToast('Copied to clipboard', 'success');
                      }}
                      title="Copy message"
                    >
                      <Copy size={13} />
                    </button>
                    <button
                      className="msg-action-btn"
                      onClick={() => handleRegenerate(message.id)}
                      title="Regenerate"
                    >
                      <RotateCcw size={13} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Real State Loading Indicator (active during isGenerating) */}
          {isGenerating && (
            <div className="message-row assistant-turn generating-turn animate-fade-in">
              <div className="limo-mascot-col">
                <div className="limo-mascot-wrap" title="Limo">
                  <LimoMascot size={42} isGenerating={true} />
                </div>
              </div>
              <div className="assistant-content-col">
                <div className="generating-indicator">
                  <ThinkingTextAnimation />
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
          background: var(--bg-header);
          transition: background-color 0.2s ease, border-color 0.2s ease;
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
          background: var(--bg-pill-active);
          border: 1px solid var(--border-subtle);
          color: var(--text-primary);
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
          transition: all 0.12s ease;
        }

        .header-action-btn:hover {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
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
          width: 100%;
        }

        .message-row.user-turn {
          display: flex;
          justify-content: flex-end;
        }

        .user-bubble-wrap {
          max-width: 80%;
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 6px;
        }

        /* User Attachments Scroll Window (Capped to show 6 items, vertical scroll for more) */
        .user-attachments-scroll-window {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 6px;
          max-height: 388px; /* Cleanly displays up to 6 items */
          overflow-y: auto;
          overflow-x: hidden;
          padding-right: 3px;
          width: 100%;
          max-width: 320px;
          box-sizing: border-box;
        }

        /* User Message Document Card (ChatGPT Style) */
        .chatgpt-file-card.user-chat-file-card {
          display: flex;
          align-items: center;
          width: 300px;
          max-width: 100%;
          height: 56px;
          border-radius: var(--radius-file-tile, 18px);
          background: var(--bg-file-tile);
          border: 1px solid var(--border-file-tile);
          padding: 8px 12px;
          gap: 10px;
          box-shadow: var(--shadow-file-tile);
          box-sizing: border-box;
          flex-shrink: 0;
          user-select: none;
        }

        .chatgpt-file-card.user-chat-file-card .file-card-meta {
          display: flex;
          flex-direction: column;
          min-width: 0;
          flex: 1;
          justify-content: center;
        }

        .chatgpt-file-card.user-chat-file-card .file-card-title {
          font-size: 13.5px;
          font-weight: 600;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.25;
        }

        .chatgpt-file-card.user-chat-file-card .file-card-subtitle {
          font-size: 12px;
          font-weight: 400;
          color: var(--text-muted);
          line-height: 1.2;
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        /* 2x2 Image Grid (ChatGPT Style) */
        .user-images-2x2-grid {
          display: grid;
          grid-template-columns: repeat(2, 126px);
          grid-template-rows: repeat(2, 126px);
          gap: 4px;
          border-radius: 18px;
          overflow: hidden;
          box-shadow: var(--shadow-file-tile);
          border: 1px solid var(--border-file-tile);
          background: var(--bg-file-tile);
          flex-shrink: 0;
        }

        .grid-2x2-item {
          width: 126px;
          height: 126px;
          overflow: hidden;
        }

        .grid-2x2-item:nth-child(1) .grid-img-el {
          border-top-left-radius: 15px;
        }
        .grid-2x2-item:nth-child(2) .grid-img-el {
          border-top-right-radius: 15px;
        }
        .grid-2x2-item:nth-child(3) .grid-img-el {
          border-bottom-left-radius: 15px;
        }
        .grid-2x2-item:nth-child(4) .grid-img-el {
          border-bottom-right-radius: 15px;
        }

        .grid-img-el {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        /* Flex Image Grid for 1-3 Images */
        .user-images-flex-grid {
          display: flex;
          flex-wrap: wrap;
          justify-content: flex-end;
          gap: 4px;
          max-width: 300px;
          flex-shrink: 0;
        }

        .user-image-bubble-card {
          border-radius: 14px;
          overflow: hidden;
          border: 1px solid var(--border-file-tile);
          box-shadow: var(--shadow-file-tile);
        }

        .user-images-flex-grid.count-1 .user-image-bubble-card {
          width: 200px;
          height: 200px;
        }

        .user-images-flex-grid.count-2 .user-image-bubble-card,
        .user-images-flex-grid.count-3 .user-image-bubble-card {
          width: 120px;
          height: 120px;
        }

        .user-message-bubble {
          background-color: var(--bg-user-bubble);
          border: 1px solid var(--border-subtle);
          color: var(--text-primary);
          font-size: 15px;
          line-height: 1.55;
          padding: 9px 16px;
          border-radius: 20px;
          word-break: break-word;
          white-space: pre-wrap;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
          display: inline-block;
        }

        .message-row.assistant-turn {
          display: flex;
          flex-direction: row;
          align-items: flex-start;
          gap: 14px;
        }

        .limo-mascot-col {
          flex-shrink: 0;
          display: flex;
          align-items: flex-start;
          padding-top: 2px;
        }

        .limo-mascot-wrap {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
          flex-shrink: 0;
        }

        .limo-mascot-wrap:hover {
          transform: scale(1.08);
        }

        .limo-mascot-wrap svg {
          width: 42px;
          height: 42px;
          display: block;
        }

        .message-row.assistant-turn.generating-turn {
          align-items: center;
        }

        .generating-turn .limo-mascot-col {
          padding-top: 0;
          align-items: center;
          height: 42px;
        }

        .generating-turn .assistant-content-col {
          justify-content: center;
          gap: 0;
        }

        .assistant-content-col {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .assistant-turn .message-content-text {
          color: var(--text-primary);
          font-size: 14.5px;
          line-height: 1.65;
        }

        .thinking-accordion {
          background: var(--bg-pill);
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
          transition: all 0.12s ease;
        }

        .thinking-toggle-btn:hover {
          color: var(--text-primary);
          background: var(--bg-pill-hover);
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
          border-top: 1px solid var(--border-subtle);
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
          background: var(--border-medium);
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
          background: var(--bg-card);
          border: 1px solid var(--border-medium);
          border-radius: var(--radius-card);
          padding: 16px 18px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-width: 520px;
          transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.2s ease;
          box-shadow: var(--shadow-card);
        }

        .artifact-card:hover {
          border-color: var(--border-focus);
          box-shadow: var(--shadow-composer);
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
        .artifact-icon-image { color: #ec4899; }
        .artifact-icon-website { color: #38bdf8; }
        .artifact-icon-code { color: #fb923c; }

        .artifact-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .format-badge {
          font-size: 11px;
          font-weight: 600;
          background: var(--bg-pill-hover);
          border: 1px solid var(--border-subtle);
          color: var(--text-secondary);
          padding: 2px 8px;
          border-radius: 4px;
          white-space: nowrap;
          flex-shrink: 0;
          letter-spacing: 0.3px;
        }

        .artifact-subagent-summary {
          font-size: 12.5px;
          line-height: 1.5;
          color: var(--text-muted);
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
          color: var(--send-btn-text-active);
          background: var(--send-btn-bg-active);
          border: 1px solid var(--border-medium);
          cursor: pointer;
          transition: all 0.15s ease;
          box-shadow: var(--shadow-card);
        }

        .artifact-edit-pill:hover {
          background: var(--send-btn-bg-hover);
          transform: translateY(-1px);
        }

        .artifact-edit-pill:active {
          transform: translateY(0);
        }

        /* Clean ChatGPT-Style Image Output */
        .clean-image-deliverable {
          position: relative;
          align-self: flex-start;
          display: inline-flex;
          width: fit-content;
          max-width: 100%;
          border-radius: 18px;
          overflow: hidden;
          line-height: 0;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
          cursor: pointer;
          transition: box-shadow 0.2s ease;
        }

        .clean-image-deliverable:hover {
          box-shadow: 0 8px 28px rgba(0, 0, 0, 0.16);
        }

        .clean-image-img {
          display: block;
          width: auto;
          height: auto;
          max-width: 100%;
          max-height: 540px;
          object-fit: contain;
          border-radius: 18px;
          filter: none;
          opacity: 1;
          transition: none;
        }

        /* Crucial: image stays 100% sharp, bright and unaffected during hover */
        .clean-image-deliverable:hover .clean-image-img {
          filter: none !important;
          opacity: 1 !important;
          transform: none !important;
        }

        .clean-image-deliverable:hover .image-download-btn,
        .clean-image-deliverable.is-hovered .image-download-btn {
          opacity: 1;
          visibility: visible;
          pointer-events: auto;
          transform: translateY(0);
        }

        .image-artifact-fallback {
          width: 240px;
          height: 180px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          background: var(--bg-thumbnail);
          color: var(--text-muted);
          border-radius: 18px;
        }

        /* Small, compact top-right download button (ChatGPT style interaction) */
        .image-download-btn {
          position: absolute;
          top: 12px;
          right: 12px;
          z-index: 10;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(20, 20, 19, 0.72);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.22);
          color: #ffffff;
          cursor: pointer;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
          opacity: 0;
          visibility: hidden;
          pointer-events: none;
          transform: translateY(-2px);
          transition: opacity 0.18s ease, visibility 0.18s ease, transform 0.18s ease, background-color 0.15s ease, border-color 0.15s ease;
        }

        .image-download-btn:hover {
          background: rgba(20, 20, 19, 0.92);
          border-color: rgba(255, 255, 255, 0.4);
          transform: translateY(0) scale(1.06);
        }

        .image-download-btn:active {
          transform: translateY(0) scale(0.96);
        }

        .artifact-thumbnail-container {
          position: relative;
          width: 190px;
          height: 118px;
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-thumbnail);
          border: 1px solid var(--border-subtle);
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
          background: var(--bg-thumbnail);
          color: var(--text-muted);
        }

        .fallback-ext {
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.5px;
          color: var(--text-muted);
        }

        .artifact-thumbnail-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0, 0, 0, 0.35);
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
          background: var(--send-btn-bg-active);
          border: 1px solid var(--border-medium);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--send-btn-text-active);
          box-shadow: var(--shadow-card);
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
          transition: all 0.12s ease;
        }

        .msg-action-btn:hover {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
        }

        .generating-indicator {
          display: flex;
          align-items: center;
          min-height: 42px;
          line-height: 1;
        }

        .thinking-text-stream {
          display: inline-flex;
          align-items: center;
          user-select: none;
        }

        .thinking-text-shimmer {
          font-size: 14.5px;
          font-weight: 500;
          letter-spacing: -0.01em;
          background: linear-gradient(
            90deg,
            var(--text-secondary) 0%,
            #60a5fa 35%,
            #a78bfa 50%,
            var(--text-secondary) 70%
          );
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: textShimmer 3s ease-in-out infinite;
          display: inline-block;
          transition: opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1), transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        [data-theme="light"] .thinking-text-shimmer {
          background: linear-gradient(
            90deg,
            #475569 0%,
            #2563eb 35%,
            #7c3aed 50%,
            #475569 70%
          );
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .thinking-text-shimmer.phase-fading {
          opacity: 0;
          transform: translateY(2px);
        }

        .thinking-text-shimmer.phase-visible {
          opacity: 1;
          transform: translateY(0);
        }

        @keyframes textShimmer {
          0% {
            background-position: 100% center;
          }
          100% {
            background-position: -100% center;
          }
        }

        .chat-bottom-composer-wrap {
          padding: 12px 24px 24px 24px;
          background: linear-gradient(to top, var(--bg-canvas) 85%, transparent 100%);
        }
      `}</style>
    </div>
  );
};
