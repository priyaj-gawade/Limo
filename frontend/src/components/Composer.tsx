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
  Paperclip,
  Loader2,
  Check,
  Volume2,
  Image as ImageIcon
} from 'lucide-react';
import { FeatureMode, ModelSpeed, AttachmentFile, VoiceOption, VoiceCatalogResponse } from '../types';
import { getFileCategory, getCategorySubtitle, renderAttachmentBadge } from '../utils/attachmentUtils';
import { useToast } from '../context/ToastContext';

interface ComposerProps {
  mode: FeatureMode;
  onClearMode: () => void;
  onSend: (
    text: string,
    attachments: AttachmentFile[],
    speed: ModelSpeed,
    voiceConfig?: { provider: string; voice_id: string; speed?: number }
  ) => void;
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
  const [attachments, setAttachments] = useState<AttachmentFile[]>([]);
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<VoiceOption | null>(null);
  const [voiceMenuOpen, setVoiceMenuOpen] = useState(false);
  const { showToast } = useToast();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const voiceMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/api/v1/voices')
      .then((res) => {
        if (!res.ok) throw new Error(`Status ${res.status}`);
        return res.json();
      })
      .then((data: VoiceCatalogResponse) => {
        if (data && data.voices && data.voices.length > 0) {
          // Check if running inside offline desktop Electron app
          const isDesktopApp = typeof window !== 'undefined' && Boolean(
            (window as any).electron ||
            (window as any).electronAPI ||
            navigator.userAgent.includes('Electron') ||
            (window as any).__LIMO_DESKTOP__
          );

          // On deployed web version, only active and working edge_tts voices are shown.
          // Azure, OpenAI, and Piper remain available in the offline/desktop environment.
          const availableVoices = isDesktopApp
            ? data.voices
            : data.voices.filter((v) => v.provider === 'edge_tts');

          setVoices(availableVoices);
          const def = availableVoices.find((v) => v.is_configured_default) || availableVoices[0];
          setSelectedVoice(def);
        }
      })
      .catch((err) => {
        console.warn('Voice catalog fetch fallback:', err);
      });
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (voiceMenuRef.current && !voiceMenuRef.current.contains(e.target as Node)) {
        setVoiceMenuOpen(false);
      }
    };
    if (voiceMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [voiceMenuOpen]);

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

  const hasInFlightUploads = attachments.some((a) => a.uploadStatus === 'uploading');

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if ((!text.trim() && attachments.length === 0) || disabled || hasInFlightUploads) return;
    const voiceConfig = selectedVoice
      ? { provider: selectedVoice.provider, voice_id: selectedVoice.voice_id }
      : undefined;
    onSend(text.trim(), attachments, speed, voiceConfig);
    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const addFiles = (fileList: File[]) => {
    if (!fileList || fileList.length === 0) return;

    const newAttachments: AttachmentFile[] = fileList.map((f) => {
      const category = getFileCategory(f.name, f.type);
      const isImg = category === 'image';
      return {
        id: `att-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        name: f.name,
        size: f.size,
        type: f.type || 'application/octet-stream',
        fileCategory: category,
        previewUrl: isImg ? URL.createObjectURL(f) : undefined,
        uploadStatus: 'uploading',
      };
    });

    setAttachments((prev) => [...prev, ...newAttachments]);
    if (fileInputRef.current) fileInputRef.current.value = '';

    // Asynchronously upload each file immediately to persist in D5 storage
    fileList.forEach((file, idx) => {
      const attId = newAttachments[idx].id;
      const formData = new FormData();
      formData.append('file', file);
      fetch('/api/v1/sources/upload', {
        method: 'POST',
        body: formData,
      })
        .then(async (res) => {
          if (res.ok) {
            const data = await res.json();
            setAttachments((prev) =>
              prev.map((a) =>
                a.id === attId
                  ? { ...a, sourceId: data.id, uploadStatus: 'done' }
                  : a
              )
            );
          } else {
            setAttachments((prev) =>
              prev.map((a) =>
                a.id === attId
                  ? { ...a, uploadStatus: 'error', error: 'Upload failed' }
                  : a
              )
            );
          }
        })
        .catch((err) => {
          console.error('Source upload failed:', err);
          setAttachments((prev) =>
            prev.map((a) =>
              a.id === attId
                ? { ...a, uploadStatus: 'error', error: 'Network error' }
                : a
            )
          );
        });
    });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      addFiles(Array.from(files));
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      e.preventDefault();
      addFiles(Array.from(e.clipboardData.files));
    }
  };

  const handleAttachmentsWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (e.deltaY !== 0) {
      e.currentTarget.scrollLeft += e.deltaY;
    }
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
      case 'audio':
        return { label: 'Audio', icon: <Volume2 size={13} />, placeholder: 'Describe the audio topic, voice narration script, or paste text to read aloud...' };
      case 'image':
        return { label: 'Image', icon: <ImageIcon size={13} />, placeholder: 'Describe the image, infographic, or visual to generate...' };
      case 'websites':
        return { label: 'Websites', icon: <Globe size={13} />, placeholder: 'Describe the website, web page, or application interface to create...' };
      case 'code':
        return { label: 'Code', icon: <Code2 size={13} />, placeholder: 'Describe the code feature, script, or algorithm to implement...' };
      default:
        return { label: '', icon: null, placeholder: 'Ask anything, or describe a document, slides, sheet, or Markdown to create...' };
    }
  };

  const modeInfo = getModeInfo(mode);
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled && !hasInFlightUploads;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  return (
    <div className="limo-composer-container">
      <div
        className="limo-composer-card"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {/* Active Mode Pill inside composer with proper Lucide X */}
        {mode !== 'none' && mode !== 'audio' && (
          <div className="composer-mode-banner">
            <div className="active-mode-pill">
              {modeInfo.icon}
              <span className="pill-mode-name">{modeInfo.label}</span>
              <button
                className="pill-close-btn"
                onClick={onClearMode}
                title="Remove creation mode"
                aria-label={`Remove ${modeInfo.label} mode`}
              >
                <X size={12} />
              </button>
            </div>
            <span className="mode-status-hint">Creation mode active</span>
          </div>
        )}

        {/* Attachment Window (Horizontal page scroll, items hide behind boundaries) */}
        {attachments.length > 0 && (
          <div
            className="composer-attachments-window slim-scrollbar"
            onWheel={handleAttachmentsWheel}
          >
            {attachments.map((file) => {
              const category = file.fileCategory || getFileCategory(file.name, file.type);
              const isImage = category === 'image' && file.previewUrl;

              if (isImage) {
                return (
                  <div key={file.id} className="composer-image-thumb-card">
                    <img src={file.previewUrl} alt={file.name} className="composer-image-preview" />
                    {file.uploadStatus === 'uploading' && (
                      <div className="thumb-upload-overlay">
                        <Loader2 size={13} className="spinning" />
                      </div>
                    )}
                    <button
                      type="button"
                      className="thumb-close-btn"
                      onClick={() => removeAttachment(file.id)}
                      title={`Remove ${file.name}`}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={11} />
                    </button>
                  </div>
                );
              }

              return (
                <div key={file.id} className={`chatgpt-file-card ${file.uploadStatus || 'done'}`}>
                  <div className="file-card-badge-wrap">
                    {renderAttachmentBadge(category)}
                  </div>
                  <div className="file-card-meta">
                    <div className="file-card-title" title={file.name}>{file.name}</div>
                    <div className="file-card-subtitle">
                      {getCategorySubtitle(category, file.name)}
                      {file.uploadStatus === 'uploading' && (
                        <span className="file-card-status uploading"> • Uploading...</span>
                      )}
                      {file.uploadStatus === 'error' && (
                        <span className="file-card-status error"> • Failed</span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="file-card-remove-btn"
                    onClick={() => removeAttachment(file.id)}
                    title={`Remove ${file.name}`}
                    aria-label={`Remove ${file.name}`}
                  >
                    <X size={13} />
                  </button>
                </div>
              );
            })}
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
          onPaste={handlePaste}
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
              aria-label="Add attachment"
            >
              <Plus size={18} />
            </button>

            {/* Audio Mode Specific Controls: Mode Pill & Contextual Voice Selector */}
            {mode === 'audio' && (
              <>
                <div className="active-mode-pill audio-mode-pill" title="Audio creation mode active">
                  <Volume2 size={13} />
                  <span className="pill-mode-name">Audio</span>
                  <button
                    className="pill-close-btn"
                    onClick={onClearMode}
                    title="Remove Audio mode"
                    aria-label="Remove Audio creation mode"
                  >
                    <X size={12} />
                  </button>
                </div>

                {/* Voice Selector (ElevenLabs style) - Contextual to Audio Mode */}
                <div className="voice-dropdown-wrapper" ref={voiceMenuRef}>
                  <button
                    type="button"
                    className="voice-selector-btn"
                    onClick={() => setVoiceMenuOpen(!voiceMenuOpen)}
                    title="Select Voice & Narration Engine"
                    aria-label="Select Voice & Narration Engine"
                  >
                    <Volume2 size={14} className="voice-icon" />
                    <span className="voice-name">
                      {selectedVoice ? selectedVoice.display_name : 'Voice'}
                    </span>
                    {selectedVoice && (
                      <span className={`voice-provider-tag ${selectedVoice.provider}`}>
                        {selectedVoice.provider === 'edge_tts' ? 'Edge' : selectedVoice.provider}
                      </span>
                    )}
                    <ChevronDown size={12} className="voice-chevron" />
                  </button>

                  {voiceMenuOpen && (
                    <div className="voice-dropdown-menu animate-fade-in">
                      <div className="voice-dropdown-header">Voice & Narration</div>

                      {/* Primary Voices (Offline/Desktop or configured external APIs) */}
                      {voices.some(v => v.provider !== 'edge_tts') && (
                        <>
                          <div className="voice-section-title">Primary Engines</div>
                          {voices.filter(v => v.provider !== 'edge_tts').map((v) => {
                            const isSel = selectedVoice?.voice_id === v.voice_id && selectedVoice?.provider === v.provider;
                            return (
                              <div
                                key={`${v.provider}-${v.voice_id}`}
                                className={`voice-option ${isSel ? 'selected' : ''}`}
                                onClick={() => {
                                  setSelectedVoice(v);
                                  setVoiceMenuOpen(false);
                                }}
                              >
                                <div className="voice-opt-left">
                                  <span className="voice-opt-name">{v.display_name}</span>
                                  <span className="voice-opt-lang">{v.language}</span>
                                </div>
                                <div className="voice-opt-right">
                                  <span className={`voice-opt-badge ${v.provider}`}>
                                    {v.provider}
                                  </span>
                                  {isSel && <Check size={13} className="voice-opt-check" />}
                                </div>
                              </div>
                            );
                          })}
                        </>
                      )}

                      {/* Edge TTS Voices */}
                      {voices.some(v => v.provider === 'edge_tts') && (
                        <>
                          {voices.some(v => v.provider !== 'edge_tts') && (
                            <div className="voice-section-title">Fallback Engines</div>
                          )}
                          {voices.filter(v => v.provider === 'edge_tts').map((v) => {
                            const isSel = selectedVoice?.voice_id === v.voice_id && selectedVoice?.provider === v.provider;
                            return (
                              <div
                                key={`${v.provider}-${v.voice_id}`}
                                className={`voice-option ${isSel ? 'selected' : ''}`}
                                onClick={() => {
                                  setSelectedVoice(v);
                                  setVoiceMenuOpen(false);
                                }}
                              >
                                <div className="voice-opt-left">
                                  <span className="voice-opt-name">{v.display_name}</span>
                                  <span className="voice-opt-lang">{v.language}</span>
                                </div>
                                <div className="voice-opt-right">
                                  <span className="voice-opt-badge edge_tts">
                                    Edge
                                  </span>
                                  {isSel && <Check size={13} className="voice-opt-check" />}
                                </div>
                              </div>
                            );
                          })}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
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

            {/* Circular Send Button or Generate Pill in Creation Mode */}
            <button
              className={`send-button ${canSend ? 'active' : 'disabled'} ${mode !== 'none' ? 'generate-mode' : ''}`}
              onClick={handleSend}
              disabled={!canSend}
              title={mode === 'none' ? "Send prompt (Enter)" : `Generate ${modeInfo.label}`}
              aria-label={mode === 'none' ? "Send prompt" : `Generate ${modeInfo.label}`}
            >
              {mode !== 'none' ? (
                <>
                  <span className="generate-text">Generate</span>
                  <ArrowUp size={15} />
                </>
              ) : (
                <ArrowUp size={18} />
              )}
            </button>
          </div>
        </div>

        {/* Bottom Metadata Bar: Project & Context */}
        <div className="composer-meta-row">
          <button
            className="meta-dropdown-btn"
            onClick={() => showToast('Project Context: Select or switch project workspace', 'info')}
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
          transition: border-color 0.18s ease, box-shadow 0.18s ease, background-color 0.2s ease;
        }

        .limo-composer-card:focus-within {
          border-color: var(--border-focus);
          box-shadow: var(--shadow-composer);
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
          background: var(--bg-pill-active);
          border: 1px solid var(--border-medium);
          color: var(--text-primary);
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
          color: var(--text-primary);
          background: var(--bg-pill-hover);
        }

        .active-mode-pill.audio-mode-pill {
          background: rgba(245, 158, 11, 0.12);
          border: 1px solid rgba(245, 158, 11, 0.28);
          color: #d97706;
        }

        .active-mode-pill.audio-mode-pill:hover {
          background: rgba(245, 158, 11, 0.18);
          border-color: rgba(245, 158, 11, 0.4);
        }

        .active-mode-pill.audio-mode-pill .pill-close-btn {
          color: rgba(217, 119, 6, 0.7);
        }

        .active-mode-pill.audio-mode-pill .pill-close-btn:hover {
          color: #d97706;
          background: rgba(245, 158, 11, 0.2);
        }

        .mode-status-hint {
          font-size: 11px;
          color: var(--text-muted);
        }

        /* Attachment Window (Horizontal page scroll, clips at chatbox boundary) */
        .composer-attachments-window {
          display: flex;
          flex-direction: row;
          flex-wrap: nowrap;
          gap: 10px;
          overflow-x: auto;
          overflow-y: hidden;
          width: 100%;
          max-width: 100%;
          padding: 2px 2px 8px 2px;
          box-sizing: border-box;
          align-items: center;
          scroll-behavior: smooth;
          -webkit-overflow-scrolling: touch;
        }

        /* Image Thumbnail in Composer */
        .composer-image-thumb-card {
          width: 56px;
          height: 56px;
          border-radius: 12px;
          overflow: hidden;
          position: relative;
          flex-shrink: 0;
          border: 1px solid var(--border-file-tile);
          background: var(--bg-card);
          box-shadow: var(--shadow-file-tile);
        }

        .composer-image-preview {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        .thumb-upload-overlay {
          position: absolute;
          inset: 0;
          background: rgba(0, 0, 0, 0.45);
          display: flex;
          align-items: center;
          justify-content: center;
          color: #ffffff;
        }

        .thumb-close-btn {
          position: absolute;
          top: 3px;
          right: 3px;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: rgba(0, 0, 0, 0.68);
          color: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
          border: none;
          cursor: pointer;
          transition: background 0.15s ease, transform 0.1s ease;
          padding: 0;
        }

        .thumb-close-btn:hover {
          background: rgba(0, 0, 0, 0.9);
          transform: scale(1.08);
        }

        /* ChatGPT Document Card in Composer */
        .chatgpt-file-card {
          display: flex;
          align-items: center;
          width: 290px;
          max-width: 290px;
          min-width: 260px;
          height: 56px;
          border-radius: var(--radius-file-tile, 18px);
          background: var(--bg-file-tile);
          border: 1px solid var(--border-file-tile);
          padding: 8px 12px;
          gap: 10px;
          flex-shrink: 0;
          box-shadow: var(--shadow-file-tile);
          transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
          box-sizing: border-box;
          user-select: none;
        }

        .chatgpt-file-card:hover {
          background: var(--bg-file-tile-hover);
          border-color: var(--border-file-tile-hover);
        }

        .file-card-badge-wrap {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .file-card-meta {
          display: flex;
          flex-direction: column;
          min-width: 0;
          flex: 1;
          justify-content: center;
        }

        .file-card-title {
          font-size: 13.5px;
          font-weight: 600;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.25;
        }

        .file-card-subtitle {
          font-size: 12px;
          font-weight: 400;
          color: var(--text-muted);
          line-height: 1.2;
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .file-card-status.uploading {
          color: var(--accent-blue);
        }

        .file-card-status.error {
          color: #ef4444;
        }

        .file-card-remove-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          flex-shrink: 0;
          transition: background 0.15s ease, color 0.15s ease;
          padding: 0;
        }

        .file-card-remove-btn:hover {
          color: var(--text-primary);
          background: var(--bg-pill-hover);
        }

        .chip-icon.spinning {
          animation: spin 1s linear infinite;
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
          background: var(--bg-pill-hover);
        }

        .voice-dropdown-wrapper {
          position: relative;
        }

        .voice-selector-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          background: var(--bg-pill);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-pill);
          color: var(--text-secondary);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          padding: 4px 10px;
          transition: all 0.14s ease;
        }

        .voice-selector-btn:hover {
          color: var(--text-primary);
          background: var(--bg-pill-hover);
          border-color: var(--border-focus);
        }

        .voice-icon {
          color: var(--accent-orange, #f59e0b);
        }

        .voice-name {
          color: var(--text-primary);
          font-weight: 500;
          max-width: 90px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .voice-provider-tag {
          font-size: 10px;
          padding: 1px 5px;
          border-radius: 4px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          font-weight: 600;
          background: var(--bg-pill);
          color: var(--text-muted);
        }

        .voice-provider-tag.azure {
          background: rgba(59, 130, 246, 0.15);
          color: #3b82f6;
        }

        .voice-provider-tag.openai {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
        }

        .voice-provider-tag.piper {
          background: rgba(168, 85, 247, 0.15);
          color: #8b5cf6;
        }

        .voice-provider-tag.edge_tts {
          background: rgba(245, 158, 11, 0.15);
          color: #d97706;
        }

        .voice-chevron {
          color: var(--text-muted);
        }

        .voice-dropdown-menu {
          position: absolute;
          bottom: calc(100% + 8px);
          left: 0;
          width: 260px;
          max-height: 320px;
          overflow-y: auto;
          background: var(--bg-dropdown);
          border: 1px solid var(--border-medium);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-dropdown);
          padding: 6px;
          z-index: 60;
        }

        .voice-dropdown-header {
          padding: 6px 10px 4px 10px;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
        }

        .voice-section-title {
          padding: 6px 10px 2px 10px;
          font-size: 10px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .voice-option {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 7px 10px;
          border-radius: var(--radius-md);
          cursor: pointer;
          transition: background 0.12s ease;
        }

        .voice-option:hover {
          background: var(--bg-sidebar-hover);
        }

        .voice-option.selected {
          background: var(--bg-sidebar-active);
        }

        .voice-opt-left {
          display: flex;
          flex-direction: column;
          gap: 1px;
        }

        .voice-opt-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .voice-opt-lang {
          font-size: 10px;
          color: var(--text-muted);
        }

        .voice-opt-right {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .voice-opt-badge {
          font-size: 9px;
          font-weight: 700;
          padding: 2px 5px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        .voice-opt-badge.azure {
          background: rgba(59, 130, 246, 0.15);
          color: #3b82f6;
        }

        .voice-opt-badge.openai {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
        }

        .voice-opt-badge.piper {
          background: rgba(168, 85, 247, 0.15);
          color: #8b5cf6;
        }

        .voice-opt-badge.edge_tts {
          background: rgba(245, 158, 11, 0.15);
          color: #d97706;
        }

        .voice-opt-check {
          color: var(--accent-orange, #f59e0b);
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
          background: var(--bg-sidebar-hover);
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
          background: var(--bg-dropdown);
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
          background: var(--bg-sidebar-hover);
        }

        .speed-option.selected {
          background: var(--bg-sidebar-active);
        }

        .speed-opt-header {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-primary);
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
          background: var(--send-btn-bg-disabled);
          color: var(--send-btn-text-disabled);
          cursor: not-allowed;
        }

        .send-button.active {
          background: var(--send-btn-bg-active);
          color: var(--send-btn-text-active);
          cursor: pointer;
          box-shadow: var(--shadow-card);
        }

        .send-button.active:hover {
          transform: scale(1.05);
          background: var(--send-btn-bg-hover);
        }

        .send-button.generate-mode {
          width: auto;
          height: 34px;
          border-radius: var(--radius-pill);
          padding: 0 14px;
          gap: 6px;
        }

        .generate-text {
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.01em;
        }

        .composer-meta-row {
          display: flex;
          align-items: center;
          gap: 16px;
          padding-top: 8px;
          border-top: 1px solid var(--border-subtle);
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
          background: var(--bg-sidebar-hover);
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
