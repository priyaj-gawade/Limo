import React, { useState } from 'react';
import { marked, Tokens } from 'marked';
import { Copy, Check, ExternalLink, Play } from 'lucide-react';
import { useToast } from '../context/ToastContext';

interface MarkdownMessageProps {
  content: string;
  className?: string;
}

// Sub-component for code blocks with interactive copy & language tag
const CodeBlock: React.FC<{ code: string; lang?: string }> = ({ code, lang }) => {
  const [copied, setCopied] = useState(false);
  const { showToast } = useToast();

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    showToast('Code copied to clipboard', 'success', 2200);
    setTimeout(() => setCopied(false), 2000);
  };

  const displayLang = lang ? lang.trim().toLowerCase() : 'text';

  return (
    <div className="md-code-block-container">
      <div className="md-code-block-header">
        <span className="md-code-lang">{displayLang}</span>
        <button
          className="md-code-copy-btn"
          onClick={handleCopy}
          type="button"
          aria-label="Copy code to clipboard"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check size={13} className="copy-icon-success" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy size={13} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="md-code-pre slim-scrollbar">
        <code className={`language-${displayLang}`}>{code}</code>
      </pre>
    </div>
  );
};

export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content, className = '' }) => {
  if (!content) return null;

  let tokens: ReturnType<typeof marked.lexer>;
  try {
    // marked.lexer splits markdown text into AST block & inline tokens
    tokens = marked.lexer(content);
  } catch (err) {
    console.error('Error parsing markdown tokens:', err);
    return <div className={`md-fallback-text ${className}`}>{content}</div>;
  }

  const renderInlineToken = (token: any, key: number | string): React.ReactNode => {
    if (!token) return null;

    switch (token.type) {
      case 'strong':
        return (
          <strong key={key} className="md-strong">
            {token.tokens ? token.tokens.map(renderInlineToken) : token.text}
          </strong>
        );
      case 'em':
        return (
          <em key={key} className="md-em">
            {token.tokens ? token.tokens.map(renderInlineToken) : token.text}
          </em>
        );
      case 'codespan':
        return (
          <code key={key} className="md-inline-code">
            {token.text}
          </code>
        );
      case 'link': {
        const isYouTube = Boolean(token.href && (token.href.includes('youtube.com') || token.href.includes('youtu.be')));
        return (
          <a
            key={key}
            href={token.href}
            title={token.title || undefined}
            target="_blank"
            rel="noopener noreferrer"
            className={`md-link ${isYouTube ? 'md-youtube-link' : ''}`}
          >
            {isYouTube && (
              <Play
                size={11}
                className="inline-play-icon"
                style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px', fill: 'currentColor' }}
              />
            )}
            {token.tokens ? token.tokens.map(renderInlineToken) : token.text}
            <ExternalLink
              size={11}
              style={{ display: 'inline', marginLeft: '3px', verticalAlign: '-1px', opacity: 0.65 }}
            />
          </a>
        );
      }
      case 'del':
        return (
          <del key={key} className="md-del">
            {token.tokens ? token.tokens.map(renderInlineToken) : token.text}
          </del>
        );
      case 'br':
        return <br key={key} />;
      case 'escape':
        return token.text;
      case 'text':
        if (token.tokens && token.tokens.length > 0) {
          return (
            <React.Fragment key={key}>
              {token.tokens.map(renderInlineToken)}
            </React.Fragment>
          );
        }
        return token.text;
      case 'html':
        // Strip or render safe text to avoid raw HTML injection
        return token.text || token.raw;
      default:
        if (token.tokens && Array.isArray(token.tokens)) {
          return (
            <React.Fragment key={key}>
              {token.tokens.map(renderInlineToken)}
            </React.Fragment>
          );
        }
        return token.text || token.raw || null;
    }
  };

  const renderBlockToken = (token: any, key: number | string): React.ReactNode => {
    if (!token) return null;

    switch (token.type) {
      case 'space':
        return null;

      case 'heading': {
        const headingContent = token.tokens
          ? token.tokens.map(renderInlineToken)
          : token.text;
        switch (token.depth) {
          case 1:
            return (
              <h1 key={key} className="md-heading md-h1">
                {headingContent}
              </h1>
            );
          case 2:
            return (
              <h2 key={key} className="md-heading md-h2">
                {headingContent}
              </h2>
            );
          case 3:
            return (
              <h3 key={key} className="md-heading md-h3">
                {headingContent}
              </h3>
            );
          default:
            return (
              <h4 key={key} className="md-heading md-h4">
                {headingContent}
              </h4>
            );
        }
      }

      case 'paragraph': {
        return (
          <p key={key} className="md-paragraph">
            {token.tokens ? token.tokens.map(renderInlineToken) : token.text}
          </p>
        );
      }

      case 'blockquote': {
        return (
          <blockquote key={key} className="md-blockquote">
            {token.tokens
              ? token.tokens.map(renderBlockToken)
              : <p>{token.text}</p>}
          </blockquote>
        );
      }

      case 'hr': {
        return <hr key={key} className="md-hr" />;
      }

      case 'list': {
        const ListTag = token.ordered ? 'ol' : 'ul';
        const listClass = token.ordered
          ? 'md-list md-ordered-list'
          : 'md-list md-unordered-list';

        return (
          <ListTag
            key={key}
            start={token.ordered && token.start ? token.start : undefined}
            className={listClass}
          >
            {token.items.map((item: any, itemIdx: number) => {
              // In marked, each list item can have tokens (paragraphs, nested lists, text)
              const hasComplexTokens = item.tokens && item.tokens.some((t: any) => t.type !== 'text');
              return (
                <li key={itemIdx} className="md-list-item">
                  {hasComplexTokens
                    ? item.tokens.map((tok: any, subIdx: number) =>
                        tok.type === 'text' && tok.tokens
                          ? tok.tokens.map(renderInlineToken)
                          : renderBlockToken(tok, subIdx)
                      )
                    : item.tokens
                    ? item.tokens.map(renderInlineToken)
                    : item.text}
                </li>
              );
            })}
          </ListTag>
        );
      }

      case 'code': {
        return <CodeBlock key={key} code={token.text} lang={token.lang} />;
      }

      case 'table': {
        return (
          <div key={key} className="md-table-wrapper slim-scrollbar">
            <table className="md-table">
              {token.header && token.header.length > 0 && (
                <thead>
                  <tr>
                    {token.header.map((cell: any, cellIdx: number) => (
                      <th
                        key={cellIdx}
                        style={{ textAlign: cell.align || 'left' }}
                        className="md-th"
                      >
                        {cell.tokens ? cell.tokens.map(renderInlineToken) : cell.text}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              {token.rows && token.rows.length > 0 && (
                <tbody>
                  {token.rows.map((row: any[], rowIdx: number) => (
                    <tr key={rowIdx} className="md-tr">
                      {row.map((cell: any, cellIdx: number) => (
                        <td
                          key={cellIdx}
                          style={{ textAlign: cell.align || 'left' }}
                          className="md-td"
                        >
                          {cell.tokens ? cell.tokens.map(renderInlineToken) : cell.text}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              )}
            </table>
          </div>
        );
      }

      case 'html': {
        return (
          <div key={key} className="md-raw-html">
            {token.text || token.raw}
          </div>
        );
      }

      default: {
        if (token.tokens && Array.isArray(token.tokens)) {
          return (
            <div key={key} className="md-block-wrap">
              {token.tokens.map(renderInlineToken)}
            </div>
          );
        }
        return (
          <p key={key} className="md-paragraph">
            {token.text || token.raw}
          </p>
        );
      }
    }
  };

  return (
    <div className={`limo-markdown-body ${className}`}>
      {tokens.map((token: any, idx: number) => renderBlockToken(token, idx))}
    </div>
  );
};
