import React, { useState } from 'react';
import {
  Copy,
  Check,
  Download,
  Edit3,
  Save,
  X,
  FileText,
  Layers,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Info
} from 'lucide-react';
import { Artifact } from '../types';
import { useToast } from '../context/ToastContext';
import { toPublishablePlainText } from '../utils/socialDraftParser';

interface SocialDraftCardProps {
  artifact: Artifact;
  onDownloadArtifact?: (art: Artifact) => void;
}

export const SocialDraftCard: React.FC<SocialDraftCardProps> = ({
  artifact,
  onDownloadArtifact
}) => {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);

  // Extract draft payload from metadata or infer from artifact
  const meta = artifact.metadata || {};
  const draft = meta.social_draft || {};
  const platform = (meta.platform || draft.platform || artifact.skill || 'linkedin').toLowerCase();

  // Initial draft states
  const [editableContent, setEditableContent] = useState<string>(() => {
    return draft.content || artifact.previewContent || artifact.description || '';
  });

  const [tweets, setTweets] = useState<Array<{ tweet_number: number; text: string; char_count?: number }>>(() => {
    if (Array.isArray(draft.items) && draft.items.length > 0) {
      return draft.items;
    }
    if (Array.isArray(draft.tweets) && draft.tweets.length > 0) {
      return draft.tweets.map((t: string, i: number) => ({ tweet_number: i + 1, text: t, char_count: t.length }));
    }
    const fallbackText = draft.content || artifact.previewContent || artifact.description || '';
    if ((platform === 'twitter' || platform === 'x') && fallbackText) {
      return [{ tweet_number: 1, text: fallbackText, char_count: fallbackText.length }];
    }
    return [];
  });

  const slides = Array.isArray(draft.slides) && draft.slides.length > 0
    ? draft.slides
    : (Array.isArray(draft.items) && draft.items.length > 0 && draft.items[0]?.headline ? draft.items : []);

  // Helper to copy clean, publishable text to clipboard
  const handleCopy = () => {
    let textToCopy = editableContent;
    if (platform === 'twitter' && tweets.length > 0) {
      textToCopy = tweets.map((t) => toPublishablePlainText(t.text)).join('\n\n---\n\n');
    } else {
      textToCopy = toPublishablePlainText(textToCopy);
    }

    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    showToast(`${getPlatformLabel()} draft copied (ready to publish)`, 'success');
    setTimeout(() => setCopied(false), 2500);
  };

  const handleDownload = () => {
    if (onDownloadArtifact) {
      onDownloadArtifact(artifact);
    } else {
      const blob = new Blob([editableContent], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${artifact.title || 'social_draft'}${artifact.fileFormat || '.md'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Downloaded draft deliverable', 'info');
    }
  };

  const handleSaveEdit = () => {
    setIsEditing(false);
    showToast('Draft changes saved in session', 'success');
  };

  const getPlatformLabel = () => {
    if (platform === 'linkedin') return 'LinkedIn';
    if (platform === 'twitter' || platform === 'x') return 'X / Twitter';
    if (platform === 'instagram') return 'Instagram';
    return 'Social Media';
  };

  const renderPlatformBadge = () => {
    if (platform === 'linkedin') {
      return (
        <div className="platform-tag linkedin">
          <svg className="platform-svg-icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 8.76a1.59 1.59 0 1 0-.02-3.18 1.59 1.59 0 0 0 .02 3.18m1.39 9.74v-8.37H5.07v8.37h2.78z" />
          </svg>
          <span>LinkedIn Post</span>
        </div>
      );
    }
    if (platform === 'twitter' || platform === 'x') {
      return (
        <div className="platform-tag twitter">
          <svg className="platform-svg-icon" viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
          </svg>
          <span>X Thread</span>
        </div>
      );
    }
    if (platform === 'instagram') {
      return (
        <div className="platform-tag instagram">
          <svg className="platform-svg-icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zm0 10.162a3.999 3.999 0 1 1 0-7.998 3.999 3.999 0 0 1 0 7.998zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z" />
          </svg>
          <span>Instagram Carousel</span>
        </div>
      );
    }
    return (
      <div className="platform-tag default">
        <Sparkles size={13} />
        <span>Social Post</span>
      </div>
    );
  };

  return (
    <div className={`social-draft-card platform-${platform}`}>
      {/* Top Banner: Brand, Title, Status & Actions */}
      <div className="draft-card-header">
        <div className="draft-header-left">
          {renderPlatformBadge()}
          <span className="draft-status-pill" title="Truthful state: Never fake published">
            <span className="draft-dot" />
            Draft
          </span>
          <span className="draft-spec-meta">{artifact.stats || `${artifact.fileFormat.toUpperCase().replace(/^\./, '')} Draft`}</span>
        </div>

        <div className="draft-actions-toolbar">
          <button
            className={`draft-action-btn ${copied ? 'copied' : ''}`}
            onClick={handleCopy}
            title="Copy draft content ready to publish"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>

          <button
            className="draft-action-btn"
            onClick={handleDownload}
            title="Download draft to disk"
          >
            <Download size={13} />
            <span>Download</span>
          </button>

          <button
            className={`draft-action-btn ${isEditing ? 'active' : ''}`}
            onClick={() => (isEditing ? handleSaveEdit() : setIsEditing(true))}
            title={isEditing ? 'Save draft changes' : 'Edit draft inline'}
          >
            {isEditing ? <Save size={13} /> : <Edit3 size={13} />}
            <span>{isEditing ? 'Done' : 'Edit'}</span>
          </button>
        </div>
      </div>

      {/* Main Content Stage */}
      <div className="draft-card-body">
        {/* EDITING MODE */}
        {isEditing ? (
          <div className="draft-editor-wrapper">
            <textarea
              className="draft-editor-textarea"
              value={editableContent}
              onChange={(e) => setEditableContent(e.target.value)}
              rows={12}
              placeholder="Edit your draft copy here..."
            />
            <div className="draft-editor-footer">
              <span className="editor-char-hint">{editableContent.length} characters</span>
              <button className="editor-save-pill" onClick={handleSaveEdit}>
                <Check size={13} /> Save Edits
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* PLATFORM: LINKEDIN */}
            {platform === 'linkedin' && (
              <div className="linkedin-preview-container">
                <div className="linkedin-mock-feed">
                  <div className="feed-author-row">
                    <div className="mock-avatar">L</div>
                    <div className="mock-author-info">
                      <span className="author-name">Limo AI Creator</span>
                      <span className="author-sub">Draft Preview • Just now</span>
                    </div>
                  </div>
                  <div className="linkedin-text-content">
                    {editableContent.split('\n\n').map((para, i) => (
                      <p key={i} className="linkedin-paragraph">
                        {para}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* PLATFORM: TWITTER / X */}
            {(platform === 'twitter' || platform === 'x') && (
              <div className="twitter-preview-container">
                {tweets.length > 0 ? (
                  <div className="tweet-thread-list">
                    {tweets.map((t, idx) => (
                      <div key={idx} className="tweet-bubble-item">
                        <div className="tweet-bubble-meta">
                          <span className="tweet-badge">
                            Tweet {idx + 1} of {tweets.length}
                          </span>
                          <span
                            className={`tweet-char-pill ${
                              (t.text?.length || 0) > 280 ? 'over-limit' : ''
                            }`}
                          >
                            {t.text?.length || 0} / 280
                          </span>
                        </div>
                        <p className="tweet-bubble-text">{t.text}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="fallback-single-tweet tweet-bubble-item">
                    <div className="tweet-bubble-meta">
                      <span className="tweet-badge">Tweet 1 of 1</span>
                      <span
                        className={`tweet-char-pill ${
                          editableContent.length > 280 ? 'over-limit' : ''
                        }`}
                      >
                        {editableContent.length} / 280
                      </span>
                    </div>
                    <p className="tweet-bubble-text">{editableContent}</p>
                  </div>
                )}
              </div>
            )}

            {/* PLATFORM: INSTAGRAM */}
            {platform === 'instagram' && (
              <div className="instagram-preview-container">
                {slides.length > 0 ? (
                  <div className="ig-carousel-viewer">
                    <div className="ig-slide-card">
                      <div className="ig-slide-header">
                        <span className="ig-slide-counter">
                          Slide {activeSlideIdx + 1} of {slides.length}
                        </span>
                        <span className="ig-slide-kind">{slides[activeSlideIdx]?.type?.toUpperCase() || 'INSIGHT'}</span>
                      </div>
                      <div className="ig-slide-body">
                        <h5 className="ig-slide-headline">{slides[activeSlideIdx]?.headline}</h5>
                        {slides[activeSlideIdx]?.subheadline && (
                          <p className="ig-slide-sub">{slides[activeSlideIdx]?.subheadline}</p>
                        )}
                        {slides[activeSlideIdx]?.body && (
                          <p className="ig-slide-text">{slides[activeSlideIdx]?.body}</p>
                        )}
                      </div>
                      {slides[activeSlideIdx]?.visual_prompt && (
                        <div className="ig-slide-visual-hint">
                          <Sparkles size={12} />
                          <span>Visual Suggestion: {slides[activeSlideIdx]?.visual_prompt}</span>
                        </div>
                      )}
                    </div>

                    <div className="ig-carousel-nav">
                      <button
                        className="ig-nav-btn"
                        disabled={activeSlideIdx === 0}
                        onClick={() => setActiveSlideIdx((prev) => Math.max(0, prev - 1))}
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <div className="ig-dots">
                        {slides.map((_: unknown, i: number) => (
                          <span
                            key={i}
                            className={`ig-dot ${i === activeSlideIdx ? 'active' : ''}`}
                            onClick={() => setActiveSlideIdx(i)}
                          />
                        ))}
                      </div>
                      <button
                        className="ig-nav-btn"
                        disabled={activeSlideIdx === slides.length - 1}
                        onClick={() => setActiveSlideIdx((prev) => Math.min(slides.length - 1, prev + 1))}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>

                    {/* Instagram Caption Section */}
                    <div className="ig-caption-block">
                      <h6 className="ig-caption-title">Post Caption & Hashtags</h6>
                      <div className="ig-caption-box">
                        <pre className="ig-caption-pre">{editableContent}</pre>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="ig-caption-box">
                    <pre className="ig-caption-pre">{editableContent}</pre>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Truthful Footnote Badge */}
      <div className="draft-card-footer">
        <div className="truthful-draft-notice">
          <Info size={12} />
          <span>
            Truthful AI Draft: This deliverable is staged locally as a draft. No external publishing or fake metrics applied.
          </span>
        </div>
      </div>

      <style>{`
        .social-draft-card {
          display: flex;
          flex-direction: column;
          border-radius: 12px;
          border: 1px solid var(--border-color, rgba(255, 255, 255, 0.12));
          background: var(--bg-card, rgba(30, 32, 38, 0.95));
          margin: 12px 0;
          overflow: hidden;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
          transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        .social-draft-card:hover {
          border-color: rgba(255, 255, 255, 0.25);
          box-shadow: 0 6px 22px rgba(0, 0, 0, 0.28);
        }

        .draft-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          background: rgba(0, 0, 0, 0.18);
          border-bottom: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
          flex-wrap: wrap;
          gap: 8px;
        }

        .draft-header-left {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .platform-tag {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.2px;
        }

        .platform-tag.linkedin {
          background: rgba(10, 102, 194, 0.18);
          color: #70b5f9;
          border: 1px solid rgba(10, 102, 194, 0.35);
        }

        .platform-tag.twitter {
          background: rgba(29, 155, 240, 0.15);
          color: #71c9f8;
          border: 1px solid rgba(29, 155, 240, 0.3);
        }

        .platform-tag.instagram {
          background: linear-gradient(135deg, rgba(240, 148, 51, 0.18), rgba(220, 39, 67, 0.2));
          color: #fca5a5;
          border: 1px solid rgba(220, 39, 67, 0.35);
        }

        .platform-tag.default {
          background: rgba(120, 120, 120, 0.2);
          color: #e2e8f0;
          border: 1px solid rgba(255, 255, 255, 0.15);
        }

        .draft-status-pill {
          display: flex;
          align-items: center;
          gap: 5px;
          background: rgba(245, 158, 11, 0.15);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.3);
          font-size: 11px;
          font-weight: 600;
          padding: 2px 7px;
          border-radius: 999px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .draft-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #fbbf24;
        }

        .draft-spec-meta {
          font-size: 11px;
          color: var(--text-tertiary, #94a3b8);
          margin-left: 2px;
        }

        .draft-actions-toolbar {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .draft-action-btn {
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 5px 10px;
          border-radius: 6px;
          font-size: 11.5px;
          font-weight: 500;
          background: rgba(255, 255, 255, 0.08);
          color: var(--text-primary, #f1f5f9);
          border: 1px solid rgba(255, 255, 255, 0.12);
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .draft-action-btn:hover {
          background: rgba(255, 255, 255, 0.16);
          border-color: rgba(255, 255, 255, 0.24);
        }

        .draft-action-btn.copied {
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          border-color: rgba(16, 185, 129, 0.4);
        }

        .draft-action-btn.active {
          background: var(--accent-primary, #3b82f6);
          color: #ffffff;
        }

        .draft-card-body {
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        /* LinkedIn Feed Styling */
        .linkedin-preview-container {
          background: rgba(15, 23, 42, 0.45);
          border-radius: 8px;
          padding: 14px;
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .feed-author-row {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 12px;
        }

        .mock-avatar {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: linear-gradient(135deg, #0a66c2, #0284c7);
          color: #fff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 13px;
        }

        .mock-author-info {
          display: flex;
          flex-direction: column;
        }

        .author-name {
          font-size: 13px;
          font-weight: 600;
          color: var(--text-primary, #f8fafc);
        }

        .author-sub {
          font-size: 11px;
          color: var(--text-tertiary, #94a3b8);
        }

        .linkedin-text-content {
          font-size: 13.5px;
          line-height: 1.6;
          color: var(--text-primary, #e2e8f0);
          white-space: pre-wrap;
          word-break: break-word;
        }

        .linkedin-paragraph {
          margin-bottom: 10px;
        }

        /* Twitter Thread Styling */
        .tweet-thread-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .tweet-bubble-item {
          background: rgba(15, 23, 42, 0.5);
          border-radius: 10px;
          padding: 12px 14px;
          border: 1px solid rgba(29, 155, 240, 0.2);
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .tweet-bubble-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 11px;
        }

        .tweet-badge {
          font-weight: 600;
          color: #38bdf8;
        }

        .tweet-char-pill {
          color: var(--text-tertiary, #94a3b8);
          font-size: 10.5px;
        }

        .tweet-char-pill.over-limit {
          color: #f87171;
          font-weight: 700;
        }

        .tweet-bubble-text {
          font-size: 13px;
          line-height: 1.5;
          color: var(--text-primary, #f1f5f9);
          white-space: pre-wrap;
          word-break: break-word;
        }

        /* Instagram Carousel Styling */
        .ig-carousel-viewer {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .ig-slide-card {
          background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
          border-radius: 12px;
          border: 1px solid rgba(220, 39, 67, 0.25);
          padding: 18px;
          min-height: 160px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .ig-slide-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .ig-slide-counter {
          font-size: 11.5px;
          font-weight: 600;
          color: #f472b6;
        }

        .ig-slide-kind {
          font-size: 10px;
          letter-spacing: 0.6px;
          padding: 2px 6px;
          border-radius: 4px;
          background: rgba(244, 114, 182, 0.15);
          color: #f472b6;
          font-weight: 600;
        }

        .ig-slide-headline {
          font-size: 16px;
          font-weight: 700;
          color: #ffffff;
          margin-bottom: 6px;
        }

        .ig-slide-sub {
          font-size: 13px;
          color: #e2e8f0;
          line-height: 1.5;
        }

        .ig-slide-text {
          font-size: 13px;
          color: #cbd5e1;
          line-height: 1.5;
        }

        .ig-slide-visual-hint {
          margin-top: 14px;
          padding-top: 10px;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11.5px;
          color: #fda4af;
          font-style: italic;
        }

        .ig-carousel-nav {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 14px;
        }

        .ig-nav-btn {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          border: 1px solid rgba(255, 255, 255, 0.15);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        }

        .ig-nav-btn:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }

        .ig-dots {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .ig-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.25);
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .ig-dot.active {
          width: 14px;
          border-radius: 4px;
          background: #f472b6;
        }

        .ig-caption-block {
          margin-top: 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
          padding: 12px;
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .ig-caption-title {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-tertiary, #94a3b8);
          margin-bottom: 6px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .ig-caption-pre {
          font-family: inherit;
          font-size: 12px;
          line-height: 1.5;
          color: var(--text-primary, #e2e8f0);
          white-space: pre-wrap;
          word-break: break-word;
          margin: 0;
        }

        /* Editor Mode */
        .draft-editor-textarea {
          width: 100%;
          background: rgba(15, 23, 42, 0.7);
          border: 1px solid var(--accent-primary, #3b82f6);
          border-radius: 8px;
          color: #fff;
          padding: 10px 12px;
          font-family: inherit;
          font-size: 13px;
          line-height: 1.5;
          resize: vertical;
        }

        .draft-editor-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 6px;
        }

        .editor-char-hint {
          font-size: 11px;
          color: var(--text-tertiary, #94a3b8);
        }

        .editor-save-pill {
          display: flex;
          align-items: center;
          gap: 5px;
          background: #10b981;
          color: #fff;
          border: none;
          padding: 5px 12px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
        }

        /* Truthful Footer */
        .draft-card-footer {
          padding: 8px 14px;
          background: rgba(0, 0, 0, 0.12);
          border-top: 1px solid var(--border-color, rgba(255, 255, 255, 0.05));
        }

        .truthful-draft-notice {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 10.5px;
          color: var(--text-tertiary, #94a3b8);
        }
      `}</style>
    </div>
  );
};
