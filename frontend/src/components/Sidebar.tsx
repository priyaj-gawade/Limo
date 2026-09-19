import React from 'react';
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  FileText,
  Presentation,
  Table,
  Video,
  Volume2,
  Image as ImageIcon,
  Globe,
  Code2,
  MessageSquare,
  LayoutGrid,
  ArrowDownToLine,
  Trash2,
  Sun,
  Moon
} from 'lucide-react';
import { FeatureMode, ChatSession } from '../types';
import { useToast } from '../context/ToastContext';

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  currentView: 'limo' | 'genoffice';
  onViewChange: (view: 'limo' | 'genoffice') => void;
  onGenOfficeClick?: () => void;
  activeMode: FeatureMode;
  onSelectMode: (mode: FeatureMode) => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggleCollapse,
  currentView,
  onViewChange,
  onGenOfficeClick,
  activeMode,
  onSelectMode,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  theme,
  onToggleTheme
}) => {
  const { showToast } = useToast();
  const creationModes: { id: FeatureMode; label: string; icon: React.ReactNode; isCore: boolean }[] = [
    { id: 'docs', label: 'Docs', icon: <FileText size={17} />, isCore: true },
    { id: 'slides', label: 'Slides', icon: <Presentation size={17} />, isCore: true },
    { id: 'sheets', label: 'Sheets', icon: <Table size={17} />, isCore: true },
    { id: 'video', label: 'Video', icon: <Video size={17} />, isCore: true },
    { id: 'audio', label: 'Audio', icon: <Volume2 size={17} />, isCore: true },
    { id: 'image', label: 'Image', icon: <ImageIcon size={17} />, isCore: true },
    { id: 'websites', label: 'Websites', icon: <Globe size={17} />, isCore: false },
    { id: 'code', label: 'Code', icon: <Code2 size={17} />, isCore: false },
  ];

  return (
    <aside className={`limo-sidebar ${collapsed ? 'collapsed' : 'expanded'}`}>
      {/* Sidebar Header */}
      <div className="sidebar-header">
        {collapsed ? (
          <button
            className="collapse-toggle-btn collapsed-toggle"
            onClick={onToggleCollapse}
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <PanelLeft size={18} />
          </button>
        ) : (
          <>
            <div className="brand-badge" onClick={onNewChat} title="Limo Conversational AI">
              <div className="brand-logo-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4v16h16" />
                  <polyline points="4 12 12 12 20 4" />
                </svg>
              </div>
              <span className="brand-title">Limo</span>
            </div>

            <button
              className="collapse-toggle-btn"
              onClick={onToggleCollapse}
              title="Collapse sidebar"
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose size={17} />
            </button>
          </>
        )}
      </div>

      {/* Switcher inserted at top of side navbar */}
      <div className="sidebar-switch-wrapper">
        <div className={`sidebar-view-toggle ${collapsed ? 'collapsed' : ''}`} role="tablist">
          <button
            className={`sidebar-toggle-btn ${currentView === 'limo' ? 'active' : ''}`}
            onClick={() => onViewChange('limo')}
            title="Limo"
            aria-label="Limo"
          >
            <MessageSquare size={14} />
            {!collapsed && <span>Limo</span>}
          </button>
          <button
            className={`sidebar-toggle-btn ${currentView === 'genoffice' ? 'active' : ''}`}
            onClick={() => {
              if (onGenOfficeClick) onGenOfficeClick();
              else onViewChange('genoffice');
            }}
            title="GenOffice"
            aria-label="GenOffice"
          >
            <LayoutGrid size={14} />
            {!collapsed && <span>GenOffice</span>}
          </button>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="new-chat-wrapper">
        <button className="new-chat-btn" onClick={onNewChat} title="Start new conversation (Ctrl+K)">
          <div className="new-chat-icon-text">
            <Plus size={16} />
            {!collapsed && <span>New Chat</span>}
          </div>
          {!collapsed && <kbd className="shortcut-badge">Ctrl K</kbd>}
        </button>
      </div>

      {/* Primary Creation Modes */}
      <div className="sidebar-scrollable-content">
        <nav className="nav-group">
          {!collapsed && <div className="section-header-title">Creation Modes</div>}
          {creationModes.map((m) => {
            const isSelected = activeMode === m.id;
            return (
              <button
                key={m.id}
                className={`nav-item ${isSelected ? 'active' : ''}`}
                onClick={() => onSelectMode(isSelected ? 'none' : m.id)}
                title={m.label}
              >
                <span className="nav-icon">{m.icon}</span>
                {!collapsed && <span className="nav-label">{m.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* Chats History Section */}
        {!collapsed && (
          <div className="section-block chats-history-block">
            <div className="section-header-title">Chats</div>
            <div className="chat-history-list">
              {sessions.length === 0 ? (
                <div className="empty-history-hint">No recent chats</div>
              ) : (
                sessions.map((session) => (
                  <div
                    key={session.id}
                    className={`chat-history-item ${activeSessionId === session.id ? 'active' : ''}`}
                    onClick={() => onSelectSession(session.id)}
                    title={session.title}
                  >
                    <MessageSquare size={14} className="chat-item-icon" />
                    <span className="chat-item-title">{session.title}</span>
                    <button
                      className="delete-session-btn"
                      onClick={(e) => onDeleteSession(session.id, e)}
                      title="Delete chat"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Profile Bar */}
      <div className="sidebar-footer">
        <div className="profile-container">
          <div className="avatar-circle" title="User Profile">
            <span>P</span>
          </div>
          {!collapsed && (
            <div className="profile-info">
              <span className="user-name">Priyaj ...</span>
            </div>
          )}
        </div>

        {!collapsed && (
          <div className="footer-actions">
            <button
              className="theme-toggle-pill"
              onClick={onToggleTheme}
              title={theme === 'dark' ? "Switch to Light mode" : "Switch to Dark mode"}
              aria-label={theme === 'dark' ? "Switch to Light mode" : "Switch to Dark mode"}
            >
              {theme === 'dark' ? (
                <>
                  <Moon size={12} className="theme-pill-icon" />
                  <span>Dark</span>
                </>
              ) : (
                <>
                  <Sun size={12} className="theme-pill-icon" />
                  <span>Light</span>
                </>
              )}
            </button>
            <button
              className="download-app-btn"
              title="Download Desktop App"
              onClick={() => showToast('Limo Desktop v1.0 is installed and active', 'success')}
            >
              <ArrowDownToLine size={15} />
            </button>
          </div>
        )}
      </div>

      <style>{`
        .limo-sidebar {
          background-color: var(--bg-sidebar);
          border-right: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          height: 100%;
          transition: width 0.2s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.2s ease, border-color 0.2s ease;
          flex-shrink: 0;
          overflow: hidden;
          z-index: 30;
        }

        .limo-sidebar.expanded {
          width: var(--sidebar-width-expanded);
        }

        .limo-sidebar.collapsed {
          width: var(--sidebar-width-collapsed);
        }

        .sidebar-header {
          height: 52px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 16px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .limo-sidebar.collapsed .sidebar-header {
          padding: 0;
          justify-content: center;
        }

        .brand-badge {
          display: flex;
          align-items: center;
          gap: 10px;
          cursor: pointer;
        }

        .brand-logo-icon {
          width: 28px;
          height: 28px;
          background: var(--brand-icon-bg);
          color: var(--brand-icon-color);
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
          transition: all 0.15s ease;
        }

        .brand-title {
          font-size: 16px;
          font-weight: 700;
          color: var(--text-primary);
          letter-spacing: 0.04em;
        }

        .collapse-toggle-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 6px;
          border-radius: var(--radius-sm);
          transition: all 0.15s ease;
        }

        .collapse-toggle-btn:hover {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
        }

        .limo-sidebar.collapsed .collapse-toggle-btn {
          width: 40px;
          height: 40px;
          padding: 0;
          border-radius: var(--radius-md);
        }

        .sidebar-switch-wrapper {
          padding: 10px 14px 4px 14px;
        }

        .limo-sidebar.collapsed .sidebar-switch-wrapper {
          padding: 10px 0 6px 0;
          display: flex;
          justify-content: center;
        }

        .sidebar-view-toggle {
          display: flex;
          align-items: center;
          background: var(--bg-pill);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-pill);
          padding: 3px;
          gap: 2px;
          position: relative;
        }

        .sidebar-view-toggle.collapsed {
          flex-direction: column;
          background: var(--bg-pill);
          border: 1px solid var(--border-subtle);
          border-radius: 24px;
          padding: 4px;
          gap: 4px;
          width: 40px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }

        .sidebar-toggle-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 6px 10px;
          border-radius: var(--radius-pill);
          border: none;
          background: transparent;
          color: var(--text-secondary);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.16s ease;
          white-space: nowrap;
        }

        .sidebar-toggle-btn:hover:not(.active) {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
        }

        .sidebar-toggle-btn.active {
          color: var(--text-primary);
          background: var(--bg-sidebar-active);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
          font-weight: 600;
        }

        .sidebar-view-toggle.collapsed .sidebar-toggle-btn {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          padding: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          flex: none;
        }

        .sidebar-view-toggle.collapsed .sidebar-toggle-btn:hover:not(.active) {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
        }

        .sidebar-view-toggle.collapsed .sidebar-toggle-btn.active {
          background: var(--bg-sidebar-active);
          color: var(--text-primary);
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
        }

        .new-chat-wrapper {
          padding: 12px 14px;
        }

        .limo-sidebar.collapsed .new-chat-wrapper {
          padding: 6px 0;
          display: flex;
          justify-content: center;
        }

        .new-chat-btn {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: var(--bg-pill);
          border: 1px solid var(--border-medium);
          color: var(--text-primary);
          padding: 8px 12px;
          border-radius: var(--radius-md);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .limo-sidebar.collapsed .new-chat-btn {
          width: 40px;
          height: 40px;
          padding: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: var(--radius-md);
        }

        .new-chat-btn:hover {
          background: var(--bg-pill-hover);
          border-color: var(--border-focus);
        }

        .new-chat-icon-text {
          display: flex;
          align-items: center;
          gap: 9px;
        }

        .limo-sidebar.collapsed .new-chat-icon-text {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          gap: 0;
        }

        .shortcut-badge {
          background: var(--bg-pill);
          border: 1px solid var(--border-subtle);
          border-radius: 4px;
          font-size: 11px;
          padding: 2px 6px;
          color: var(--text-muted);
          font-family: inherit;
        }

        .sidebar-scrollable-content {
          flex: 1;
          overflow-y: auto;
          padding: 0 10px;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .limo-sidebar.collapsed .sidebar-scrollable-content {
          padding: 0;
          align-items: center;
        }

        .nav-group {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }

        .limo-sidebar.collapsed .nav-group {
          align-items: center;
          width: 100%;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 10px;
          border-radius: var(--radius-md);
          border: none;
          background: transparent;
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 450;
          cursor: pointer;
          width: 100%;
          text-align: left;
          transition: all 0.12s ease;
        }

        .limo-sidebar.collapsed .nav-item {
          width: 40px;
          height: 40px;
          padding: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto;
        }

        .nav-item:hover {
          background: var(--bg-sidebar-hover);
          color: var(--text-primary);
        }

        .nav-item.active {
          background: var(--bg-sidebar-active);
          color: var(--text-primary);
          font-weight: 600;
        }

        .nav-icon {
          flex-shrink: 0;
          color: var(--text-muted);
          transition: color 0.12s ease;
        }

        .limo-sidebar.collapsed .nav-icon {
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .nav-item:hover .nav-icon,
        .nav-item.active .nav-icon {
          color: var(--text-primary);
        }

        .nav-label {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .section-block {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .section-header-title {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 0 10px;
          margin-bottom: 2px;
        }

        .chats-history-block {
          flex: 1;
        }

        .chat-history-list {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .chat-history-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 7px 10px;
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          cursor: pointer;
          transition: all 0.12s ease;
          position: relative;
        }

        .chat-history-item:hover {
          background: var(--bg-sidebar-hover);
          color: var(--text-primary);
        }

        .chat-history-item.active {
          background: var(--bg-sidebar-active);
          color: var(--text-primary);
          font-weight: 550;
        }

        .chat-item-icon {
          flex-shrink: 0;
          color: var(--text-muted);
        }

        .chat-item-title {
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .delete-session-btn {
          opacity: 0;
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 3px;
          border-radius: 4px;
          transition: all 0.12s ease;
        }

        .chat-history-item:hover .delete-session-btn {
          opacity: 1;
        }

        .delete-session-btn:hover {
          color: #f87171;
          background: rgba(239, 68, 68, 0.15);
        }

        .empty-history-hint {
          font-size: 12px;
          color: var(--text-placeholder);
          padding: 6px 10px;
        }

        .sidebar-footer {
          height: 60px;
          border-top: 1px solid var(--border-subtle);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 14px;
          flex-shrink: 0;
        }

        .limo-sidebar.collapsed .sidebar-footer {
          padding: 0;
          justify-content: center;
        }

        .profile-container {
          display: flex;
          align-items: center;
          gap: 10px;
          cursor: pointer;
        }

        .limo-sidebar.collapsed .profile-container {
          justify-content: center;
        }

        .avatar-circle {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--avatar-bg);
          border: 1px solid var(--avatar-border);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 13px;
          font-weight: 600;
          color: var(--avatar-color);
          transition: all 0.15s ease;
        }

        .user-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .footer-actions {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .theme-toggle-pill {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          background: var(--bg-pill);
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          font-size: 11px;
          font-weight: 600;
          padding: 4px 9px;
          border-radius: var(--radius-pill);
          cursor: pointer;
          transition: all 0.15s ease;
          user-select: none;
        }

        .theme-toggle-pill:hover {
          background: var(--bg-pill-hover);
          color: var(--text-primary);
          border-color: var(--border-focus);
        }

        .theme-pill-icon {
          flex-shrink: 0;
          color: var(--text-muted);
          transition: color 0.15s ease;
        }

        .theme-toggle-pill:hover .theme-pill-icon {
          color: var(--text-primary);
        }

        .download-app-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 5px;
          border-radius: var(--radius-sm);
          transition: all 0.12s ease;
        }

        .download-app-btn:hover {
          color: var(--text-primary);
          background: var(--bg-sidebar-hover);
        }
      `}</style>
    </aside>
  );
};
