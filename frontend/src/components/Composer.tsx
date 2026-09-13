import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  ArrowUp,
  X,
  ChevronDown,
  Folder,
  FileText,
  Presentation,
  Table,
  Video,
  Globe,
  Code2,
  Paperclip
} from 'lucide-react';
import { FeatureMode, ModelSpeed, AttachmentFile } from '../types';

interface ComposerProps {
  mode: FeatureMode;
  onClearMode: () => void;
  onSend: (text: string, attachments: AttachmentFile[], speed: ModelSpeed) => void;
  disabled?: boolean;
  initialText?: string;
}

export const Composer: React.FC<ComposerProps> = ({
  mode,
  onClearMode,
  onSend,
  disabled = false,
  initialText = ''
}) => {
  const [text, setText] = useState(initialText);
  const [speed, setSpeed] = useState<ModelSpeed>('Instant');
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);
  const [attachments, setAttachments] = useState<AttachmentFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (initialText) {
      setText(initialText);
    }
  }, [initialText]);

  // Auto-resize textarea as user types
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if ((!text.trim() && attachments.length === 0) || disabled) return;
    onSend(text.trim(), attachments, speed);
    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const newAttachments: AttachmentFile[] = Array.from(files).map((f) => ({
      id: `att-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      name: f.name,
      size: f.size,
      type: f.type || 'application/octet-stream'
    }));
    setAttachments((prev) => [...prev, ...newAttachments]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const getModeInfo = (m: FeatureMode) => {
    switch (m) {
      case 'docs':
        return { label: 'Docs', icon: <FileText size={13} />, placeholder: 'Describe the document, briefing, or advisory to generate...' };
      case 'slides':
        return { label: 'Slides', icon: <Presentation size={13} />, placeholder: 'Describe the presentation topic, audience, and slide count...' };
      case 'sheets':
        return { label: 'Sheets', icon: <Table size={13} />, placeholder: 'Describe the dataset, financial model, or table to structure...' };
      case 'video':
        return { label: 'Video', icon: <Video size={13} />, placeholder: 'Describe video topic, storyboard concept, duration, and tone...' };
      case 'websites':
        return { label: 'Websites', icon: <Globe size={13} />, placeholder: 'Describe the website, web page, or application interface to create...' };
      case 'code':
        return { label: 'Code', icon: <Code2 size={13} />, placeholder: 'Describe the code feature, script, or algorithm to implement...' };
      default:
        return { label: '', icon: null, placeholder: 'Ask anything, or describe a document, slides, sheet, or Markdown to create...' };
    }
  };

  const modeInfo = getModeInfo(mode);
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  return (
    <div className="limo-composer-container">
      <div className="limo-composer-card">
        {/* Active Mode Pill inside composer with proper Lucide X */}
        {mode !== 'none' && (
          <div className="composer-mode-banner">
            <div className="active-mode-pill">
              {modeInfo.icon}
              <span className="pill-mode-name">{modeInfo.label}</span>
              <button
                className="pill-close-btn"
                onClick={onClearMode}
                title="Remove creation mode"
              >
                <X size={12} />
              </button>
            </div>
            <span className="mode-status-hint">Creation mode active</span>
          </div>
        )}

        {/* Attachment Chips row */}
        {attachments.length > 0 && (
          <div className="composer-attachments-row">
            {attachments.map((file) => (
              <div key={file.id} className="attachment-chip">
                <Paperclip size={12} className="chip-icon" />
                <span className="chip-name">{file.name}</span>
                <button
                  className="chip-remove-btn"
                  onClick={() => removeAttachment(file.id)}
                  title="Remove file"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Textarea Input */}
        <textarea
          ref={textareaRef}
          className="composer-textarea"
          rows={1}
          placeholder={modeInfo.placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />

        {/* Controls Row */}
        <div className="composer-controls-row">
          {/* Left: Attachment Trigger */}
          <div className="controls-left">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              style={{ display: 'none' }}
              multiple
            />
            <button
              className="attach-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Add attachment (PDF, DOCX, XLSX, TXT, Images)"
            >
              <Plus size={18} />
            </button>
          </div>

          {/* Right: Model Speed Selector & Send Button */}
          <div className="controls-right">
            {/* Speed Selector */}
            <div className="speed-dropdown-wrapper">
              <button
                className="speed-selector-btn"
                onClick={() => setSpeedMenuOpen(!speedMenuOpen)}
                title="Reasoning Mode Tier"
              >
                <span className="speed-label">{speed}</span>
                <span className="speed-tier">High</span>
                <ChevronDown size={14} className="speed-chevron" />
              </button>

              {speedMenuOpen && (
                <div className="speed-dropdown-menu animate-fade-in">
                  <div
                    className={`speed-option ${speed === 'Instant' ? 'selected' : ''}`}
                    onClick={() => {
                      setSpeed('Instant');
                      setSpeedMenuOpen(false);
                    }}
                  >
                    <div className="speed-opt-header">Instant</div>
                    <div className="speed-opt-desc">Fast responses for standard tasks</div>
                  </div>
                  <div
                    className={`speed-option ${speed === 'High' ? 'selected' : ''}`}
                    onClick={() => {
                      setSpeed('High');
                      setSpeedMenuOpen(false);
                    }}
                  >
                    <div className="speed-opt-header">High Reasoning</div>
                    <div className="speed-opt-desc">Deep reflection, multi-step analysis & verification</div>
                  </div>
                </div>
              )}
            </div>

            {/* Circular Send Button */}
            <button
              className={`send-button ${canSend ? 'active' : 'disabled'}`}
              onClick={handleSend}
              disabled={!canSend}
              title="Send prompt (Enter)"
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>

        {/* Bottom Metadata Bar: Project & Context */}
        <div className="composer-meta-row">
          <button
            className="meta-dropdown-btn"
            onClick={() => alert('Project Context: Select or switch project workspace')}
          >
            <Folder size={14} className="meta-icon" />
            <span>Select project</span>
            <ChevronDown size={13} className="meta-chevron" />
          </button>
        </div>
      </div>

      <style>{`
        .limo-composer-container {
          width: 100%;
          max-width: var(--composer-max-width);
          margin: 0 auto;
          position: relative;
        }

        .limo-composer-card {
          background-color: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-composer);
          box-shadow: var(--shadow-composer);
          padding: 16px 20px 12px 20px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .limo-composer-card:focus-within {
          border-color: var(--border-focus);
          box-shadow: 0 10px 36px rgba(0, 0, 0, 0.55);
        }

        .composer-mode-banner {
          display: flex;
          align-items: center;
          gap: 10px;
          padding-bottom: 6px;
        }

        .active-mode-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: rgba(255, 255, 255, 0.12);
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: #ffffff;
          padding: 4px 10px;
          border-radius: var(--radius-pill);
          font-size: 12px;
          font-weight: 500;
        }

        .pill-mode-name {
          letter-spacing: 0.02em;
        }

        .pill-close-btn {
          background: transparent;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1px;
          border-radius: 50%;
          transition: all 0.12s ease;
        }

        .pill-close-btn:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.2);
        }

        .mode-status-hint {
          font-size: 11px;
          color: var(--text-muted);
        }

        .composer-attachments-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          padding-bottom: 6px;
        }

        .attachment-chip {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(255, 255, 255, 0.07);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: var(--radius-md);
          padding: 4px 10px;
          font-size: 12px;
          color: var(--text-primary);
        }

        .chip-name {
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .chip-remove-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2px;
        }

        .chip-remove-btn:hover {
          color: #f87171;
        }

        .composer-textarea {
          width: 100%;
          background: transparent;
          border: none;
          outline: none;
          color: var(--text-primary);
          font-size: 15px;
          line-height: 1.55;
          font-family: inherit;
          resize: none;
          min-height: 38px;
          max-height: 220px;
        }

        .composer-textarea::placeholder {
          color: var(--text-placeholder);
        }

        .composer-controls-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-top: 4px;
        }

        .controls-left {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .attach-btn {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: transparent;
          border: none;
          color: var(--text-secondary);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.14s ease;
        }

        .attach-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.07);
        }

        .controls-right {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .speed-dropdown-wrapper {
          position: relative;
        }

        .speed-selector-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          background: transparent;
          border: none;
          color: var(--text-secondary);
          font-size: 13px;
          cursor: pointer;
          padding: 6px 8px;
          border-radius: var(--radius-sm);
          transition: all 0.14s ease;
        }

        .speed-selector-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        .speed-label {
          color: var(--text-primary);
          font-weight: 500;
        }

        .speed-tier {
          color: var(--text-muted);
          font-size: 12px;
        }

        .speed-chevron {
          color: var(--text-muted);
        }

        .speed-dropdown-menu {
          position: absolute;
          bottom: calc(100% + 8px);
          right: 0;
          width: 220px;
          background: #242423;
          border: 1px solid var(--border-medium);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-dropdown);
          padding: 6px;
          z-index: 50;
        }

        .speed-option {
          padding: 8px 12px;
          border-radius: var(--radius-md);
          cursor: pointer;
          transition: background 0.12s ease;
        }

        .speed-option:hover {
          background: rgba(255, 255, 255, 0.06);
        }

        .speed-option.selected {
          background: rgba(255, 255, 255, 0.1);
        }

        .speed-opt-header {
          font-size: 13px;
          font-weight: 600;
          color: #ffffff;
        }

        .speed-opt-desc {
          font-size: 11px;
          color: var(--text-secondary);
          margin-top: 2px;
        }

        .send-button {
          width: 34px;
          height: 34px;
          border-radius: 50%;
          border: none;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .send-button.disabled {
          background: rgba(255, 255, 255, 0.12);
          color: rgba(255, 255, 255, 0.28);
          cursor: not-allowed;
        }

        .send-button.active {
          background: #ffffff;
          color: #181817;
          cursor: pointer;
          box-shadow: 0 2px 10px rgba(255, 255, 255, 0.3);
        }

        .send-button.active:hover {
          transform: scale(1.05);
          background: #f4f4f3;
        }

        .composer-meta-row {
          display: flex;
          align-items: center;
          gap: 16px;
          padding-top: 8px;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .meta-dropdown-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          background: transparent;
          border: none;
          color: var(--text-secondary);
          font-size: 12px;
          cursor: pointer;
          padding: 3px 6px;
          border-radius: var(--radius-sm);
          transition: all 0.12s ease;
        }

        .meta-dropdown-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }

        .meta-icon {
          color: var(--text-muted);
        }

        .meta-chevron {
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
};
