import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { HomeScreen } from './components/HomeScreen';
import { ChatView } from './components/ChatView';
import { ConfirmModal } from './components/ConfirmModal';
import { LoginModal } from './components/LoginModal';
import { FeatureInfoModal, FeatureInfoType } from './components/FeatureInfoModal';
import { useToast } from './context/ToastContext';
import { useAuth } from './context/AuthContext';
import { LogIn } from 'lucide-react';
import { FeatureMode, ModelSpeed, AttachmentFile, ChatSession, Artifact, ChatMessage } from './types';
import { getFileCategory } from './utils/attachmentUtils';

// UI Preference Storage Keys
const SIDEBAR_PREF_KEY = 'limo_ui_sidebar_collapsed';
const ACTIVE_SESSION_KEY = 'limo_active_session_id';
const THEME_STORAGE_KEY = 'limo_theme';

export const App: React.FC = () => {
  const { user, isAuthenticated, isLoginModalOpen, openLoginModal, closeLoginModal, logout } = useAuth();
  const [currentView, setCurrentView] = useState<'limo' | 'genoffice'>('limo');
  const [featureInfoType, setFeatureInfoType] = useState<FeatureInfoType | null>(null);

  const isDesktop = (): boolean => {
    if (typeof window === 'undefined') return false;
    return Boolean(
      (window as any).electron ||
      (window as any).electronAPI ||
      navigator.userAgent.includes('Electron') ||
      (window as any).__LIMO_DESKTOP__
    );
  };

  // Theme state with localStorage persistence and system theme fallback
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light';
      }
    } catch {
      // fallback
    }
    return 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // ignore
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };
  
  // UI Preference only: sidebar collapsed state
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(SIDEBAR_PREF_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const [activeMode, setActiveMode] = useState<FeatureMode>('none');
  
  // Real application state backed by SQLite ChatService
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(ACTIVE_SESSION_KEY);
    } catch {
      return null;
    }
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const { showToast } = useToast();
  const [sessionToDelete, setSessionToDelete] = useState<{ id: string; title: string } | null>(null);

  // Save UI layout preference
  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_PREF_KEY, String(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  // Fetch messages for a specific session
  const fetchMessages = async (sessionId: string) => {
    if (!isAuthenticated) return [];
    try {
      const res = await fetch(`/api/v1/chats/${sessionId}/messages`);
      if (res.status === 401) {
        openLoginModal();
        return [];
      }
      if (res.ok) {
        const data: any[] = await res.json();
        const mapped: ChatMessage[] = data.map((m) => {
          const rawAttachments: any[] = m.attachments || [];
          const attachments: AttachmentFile[] = rawAttachments.map((att: any) => {
            const mimeType = att.mime_type || att.type || '';
            const category = getFileCategory(att.name, mimeType);
            const isImg = category === 'image';
            const sourceId = att.source_id || att.sourceId;
            const previewUrl =
              att.previewUrl ||
              (isImg && sourceId ? `/api/v1/sources/${sourceId}/download` : undefined);

            return {
              id: att.id || `att-${Math.random().toString(36).substring(2, 7)}`,
              name: att.name,
              size: att.size_bytes || att.size || 0,
              type: mimeType || 'application/octet-stream',
              sourceId,
              fileCategory: category,
              previewUrl,
              uploadStatus: 'done' as const,
            };
          });

          return {
            id: m.id,
            role: m.role,
            content: m.content,
            mode: m.mode || 'none',
            attachments,
            artifactIds: m.artifact_ids || [],
            artifacts: (m.artifacts || []).map((a: any) => ({
              id: a.id,
              title: a.title,
              type: a.artifact_type,
              description: a.description || '',
              fileFormat: a.file_format,
              sizeBytes: a.size_bytes,
              stats: a.stats,
              metadata: a.metadata,
              thumbnailUrl: `/api/v1/artifacts/${a.id}/thumbnail`,
              createdAt: a.created_at,
            })),
            executionSummary: m.execution_summary,
            createdAt: m.created_at || new Date().toISOString(),
          };
        });
        setSessions((prev) =>
          prev.map((s) => (s.id === sessionId ? { ...s, messages: mapped } : s))
        );
        return mapped;
      }
    } catch (e) {
      console.error('Failed to fetch messages for session:', sessionId, e);
    }
    return [];
  };

  // Fetch sessions list from backend on mount or auth change
  const fetchSessions = async () => {
    if (!isAuthenticated) {
      setSessions([]);
      return [];
    }
    try {
      const res = await fetch('/api/v1/chats');
      if (res.status === 401) {
        setSessions([]);
        return [];
      }
      if (res.ok) {
        const data: any[] = await res.json();
        const mapped: ChatSession[] = data.map((s) => ({
          id: s.id,
          title: s.title,
          mode: s.mode || 'none',
          messages: [],
          createdAt: s.created_at,
          updatedAt: s.updated_at,
        }));
        setSessions(mapped);
        return mapped;
      }
    } catch (e) {
      console.error('Failed to fetch chat sessions:', e);
    }
    return [];
  };

  // Initial load and restoration from SQLite conditioned on authentication
  useEffect(() => {
    if (isAuthenticated) {
      fetchSessions().then((loaded) => {
        const saved = localStorage.getItem(ACTIVE_SESSION_KEY);
        if (saved && loaded.some((s) => s.id === saved)) {
          setActiveSessionId(saved);
          const match = loaded.find((s) => s.id === saved);
          if (match) setActiveMode(match.mode);
          fetchMessages(saved);
        } else {
          setActiveSessionId(null);
          try {
            localStorage.removeItem(ACTIVE_SESSION_KEY);
          } catch {}
        }
      });
    } else {
      setSessions([]);
      setActiveSessionId(null);
      try {
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      } catch {}
    }
  }, [isAuthenticated]);

  // Global keyboard shortcut Ctrl+K / Cmd+K for new chat
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isAuthenticated]);

  const handleNewChat = () => {
    if (!isAuthenticated) {
      openLoginModal();
      showToast('Please sign in with Google to start a conversation', 'info');
      return;
    }
    setActiveSessionId(null);
    try {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    } catch {}
    setActiveMode('none');
    setCurrentView('limo');
  };

  const handleSelectMode = (mode: FeatureMode) => {
    if (!isDesktop()) {
      if (mode === 'code') {
        setFeatureInfoType('code');
        return;
      }
      if (mode === 'websites') {
        setFeatureInfoType('website');
        return;
      }
    }

    if (!isAuthenticated && mode !== 'none') {
      openLoginModal();
      showToast('Please sign in with Google to use creation modes', 'info');
      return;
    }
    setActiveMode(mode);
  };

  const handleSelectSession = (id: string) => {
    if (!isAuthenticated) {
      openLoginModal();
      return;
    }
    setActiveSessionId(id);
    try {
      localStorage.setItem(ACTIVE_SESSION_KEY, id);
    } catch {}
    const s = sessions.find((item) => item.id === id);
    if (s) {
      setActiveMode(s.mode);
    }
    setCurrentView('limo');
    fetchMessages(id);
  };

  const handleRequestDeleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const s = sessions.find((item) => item.id === id);
    setSessionToDelete({ id, title: s ? s.title : 'this chat' });
  };

  const handleConfirmDeleteSession = async () => {
    if (!sessionToDelete) return;
    const { id } = sessionToDelete;
    setSessionToDelete(null);
    try {
      await fetch(`/api/v1/chats/${id}`, { method: 'DELETE' });
      showToast('Chat deleted', 'info');
    } catch (err) {
      console.error('Failed to delete chat session:', err);
      showToast('Failed to delete chat session', 'error');
    }
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) {
      handleNewChat();
    }
  };

  // Real backend agent turn execution connecting UI to LimoAgentRuntime and Gemini LLM
  const handleSend = async (
    text: string,
    attachments: AttachmentFile[],
    speed: ModelSpeed,
    voiceConfig?: { provider: string; voice_id: string; speed?: number }
  ) => {
    // Strict authentication gate: fail closed on client before dispatching
    if (!isAuthenticated) {
      openLoginModal();
      showToast('Please sign in with Google to use Limo', 'info');
      return;
    }

    let targetSessionId = activeSessionId;
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: text,
      mode: activeMode,
      attachments,
      createdAt: new Date().toISOString(),
    };

    if (!targetSessionId) {
      try {
        const title = text.length > 36 ? `${text.substring(0, 36)}...` : text;
        const res = await fetch('/api/v1/chats', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, mode: activeMode }),
        });
        if (res.status === 401) {
          openLoginModal();
          showToast('Session expired. Please sign in again.', 'error');
          return;
        }
        if (res.ok) {
          const created = await res.json();
          targetSessionId = created.id;
          setActiveSessionId(targetSessionId);
          try {
            localStorage.setItem(ACTIVE_SESSION_KEY, created.id);
          } catch {}
          const newSession: ChatSession = {
            id: created.id,
            title: created.title,
            mode: created.mode || activeMode,
            messages: [tempUserMsg],
            createdAt: created.created_at,
            updatedAt: created.updated_at,
          };
          setSessions((prev) => [newSession, ...prev]);
        } else {
          showToast('Failed to initialize conversation session.');
          return;
        }
      } catch (err) {
        console.error('Failed to create session:', err);
        showToast('Network error initializing session.');
        return;
      }
    } else {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? { ...s, messages: [...s.messages, tempUserMsg], updatedAt: new Date().toISOString() }
            : s
        )
      );
    }

    if (!targetSessionId) return;

    setIsGenerating(true);
    try {
      const turnPayload = {
        content: text,
        mode: activeMode,
        attachments: attachments.map((a) => ({
          id: a.id,
          name: a.name,
          size_bytes: a.size,
          mime_type: a.type,
          source_id: a.sourceId || null,
        })),
        source_ids: attachments.map((a) => a.sourceId).filter(Boolean) as string[],
        voice_config: voiceConfig || null,
      };

      const turnRes = await fetch(`/api/v1/chats/${targetSessionId}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(turnPayload),
      });

      if (turnRes.status === 401) {
        setIsGenerating(false);
        openLoginModal();
        showToast('Session expired. Please sign in again.', 'error');
        return;
      }

      if (turnRes.ok) {
        await fetchMessages(targetSessionId);
      } else {
        const errData = await turnRes.json().catch(() => ({}));
        const errMsg: ChatMessage = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${errData.detail || errData.message || 'Agent reasoning failed.'}`,
          createdAt: new Date().toISOString(),
        };
        setSessions((prev) =>
          prev.map((s) =>
            s.id === targetSessionId ? { ...s, messages: [...s.messages, errMsg] } : s
          )
        );
      }
    } catch (err) {
      console.error('Turn execution error:', err);
      const errMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: 'Failed to connect to Limo AI backend service.',
        createdAt: new Date().toISOString(),
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId ? { ...s, messages: [...s.messages, errMsg] } : s
        )
      );
    } finally {
      setIsGenerating(false);
    }
  };


  const handleOpenInWorkspace = async (art: Artifact) => {
    try {
      showToast(`Opening "${art.title}${art.fileFormat}" in GenOffice...`);
      const res = await fetch(`/api/v1/artifacts/${art.id}/open`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        const method = data.details?.method || 'workspace';
        showToast(`Document opened in GenOffice (${method})`);
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(`Failed to open in GenOffice: ${err.detail || 'Service unavailable'}`);
      }
    } catch (e) {
      console.error('Error opening artifact:', e);
      showToast('Error connecting to GenOffice opener');
    }
  };

  const handleDownloadArtifact = (art: Artifact) => {
    const link = document.createElement('a');
    link.href = `/api/v1/artifacts/${art.id}/download`;
    link.download = `${art.title}${art.fileFormat}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast(`Downloading deliverable: ${art.title}${art.fileFormat}`);
  };

  const handleGenOfficeNavClick = () => {
    if (isDesktop()) {
      setCurrentView('genoffice');
    } else {
      setFeatureInfoType('office');
    }
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;

  return (
    <div className="limo-app-root">
      {/* Main Workspace Frame */}
      <div className="limo-main-frame">
        {/* Left Sidebar */}
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggleCollapse={toggleSidebar}
          currentView={currentView}
          onViewChange={setCurrentView}
          onGenOfficeClick={handleGenOfficeNavClick}
          activeMode={activeMode}
          onSelectMode={handleSelectMode}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleRequestDeleteSession}
          theme={theme}
          onToggleTheme={toggleTheme}
          user={user}
          isAuthenticated={isAuthenticated}
          onOpenLogin={openLoginModal}
          onLogout={logout}
        />

        {/* Main Conversational Stage (Zero persistent canvas, strictly chat-first) */}
        <main className="limo-conversational-stage">
          {activeSession ? (
            <ChatView
              session={activeSession}
              activeMode={activeMode}
              onSelectMode={handleSelectMode}
              onSend={handleSend}
              isGenerating={isGenerating}
              onOpenInWorkspace={handleOpenInWorkspace}
              onDownloadArtifact={handleDownloadArtifact}
            />
          ) : (
            <HomeScreen
              activeMode={activeMode}
              onSelectMode={handleSelectMode}
              onSend={handleSend}
            />
          )}
        </main>
      </div>

      {/* Accessible in-app confirmation modal for destructive session deletion */}
      <ConfirmModal
        isOpen={!!sessionToDelete}
        title="Delete Chat"
        message={`Are you sure you want to delete "${sessionToDelete?.title}"? This conversation cannot be restored.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        isDestructive={true}
        onConfirm={handleConfirmDeleteSession}
        onCancel={() => setSessionToDelete(null)}
      />

      {/* Centered Two-Column Google Login Modal */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={closeLoginModal}
      />

      {/* Three Web-Only Information Popups for Office, Code, and Website */}
      <FeatureInfoModal
        isOpen={!!featureInfoType}
        type={featureInfoType}
        onClose={() => setFeatureInfoType(null)}
      />

      <style>{`
        .limo-app-root {
          width: 100vw;
          height: 100vh;
          display: flex;
          flex-direction: column;
          background-color: var(--bg-canvas);
          color: var(--text-primary);
          overflow: hidden;
        }

        .limo-main-frame {
          flex: 1;
          display: flex;
          width: 100%;
          height: 100vh;
          overflow: hidden;
          position: relative;
        }

        .limo-conversational-stage {
          flex: 1;
          height: 100%;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          background-color: var(--bg-canvas);
          position: relative;
        }

        .stage-top-bar {
          position: absolute;
          top: 14px;
          right: 20px;
          z-index: 20;
          display: flex;
          align-items: center;
          gap: 10px;
          pointer-events: auto;
        }

        .top-login-pill-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: var(--bg-pill, #1c1d22);
          border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.12));
          color: var(--text-primary, #ffffff);
          font-size: 12px;
          font-weight: 600;
          padding: 6px 14px;
          border-radius: var(--radius-pill, 20px);
          cursor: pointer;
          transition: all 0.16s ease;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
          user-select: none;
        }

        .top-login-pill-btn:hover {
          background: var(--bg-pill-hover, #262830);
          border-color: rgba(255, 255, 255, 0.25);
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }

        .top-user-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: var(--bg-pill, #1c1d22);
          border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.12));
          padding: 4px 10px 4px 5px;
          border-radius: var(--radius-pill, 20px);
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .top-user-badge:hover {
          background: var(--bg-pill-hover, #262830);
          border-color: rgba(255, 255, 255, 0.25);
        }

        .top-user-avatar-img {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          object-fit: cover;
        }

        .top-user-avatar-placeholder {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: var(--avatar-bg, #3b82f6);
          color: #ffffff;
          font-size: 11px;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .top-user-name {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-primary);
          max-width: 110px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .limo-toast-container {
          position: fixed;
          bottom: 24px;
          right: 24px;
          z-index: 999;
          pointer-events: none;
        }

        .limo-toast-pill {
          background: var(--bg-toast);
          border: 1px solid var(--border-medium);
          color: var(--text-inverse);
          padding: 10px 18px;
          border-radius: var(--radius-pill);
          font-size: 13px;
          font-weight: 500;
          display: flex;
          align-items: center;
          gap: 10px;
          box-shadow: var(--shadow-toast);
        }

        .toast-icon-check {
          color: #4ade80;
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
};

export default App;
