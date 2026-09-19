import React from 'react';
import {
  FileText,
  Presentation,
  Table,
  Code2,
  File,
  Image as ImageIcon
} from 'lucide-react';
import { FileCategory } from '../types';

/**
 * Resolves high-level file category from file name and MIME type.
 */
export function getFileCategory(fileName: string, mimeType?: string): FileCategory {
  const name = fileName.toLowerCase();
  const ext = name.split('.').pop() || '';
  const mime = (mimeType || '').toLowerCase();

  if (
    ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg', 'bmp', 'avif'].includes(ext) ||
    mime.startsWith('image/')
  ) {
    return 'image';
  }

  if (['pptx', 'ppt', 'key'].includes(ext) || mime.includes('presentation') || mime.includes('powerpoint')) {
    return 'presentation';
  }

  if (ext === 'pdf' || mime === 'application/pdf') {
    return 'pdf';
  }

  if (
    ['xlsx', 'xls', 'csv', 'tsv', 'numbers'].includes(ext) ||
    mime.includes('spreadsheet') ||
    mime.includes('excel') ||
    mime === 'text/csv'
  ) {
    return 'spreadsheet';
  }

  if (
    ['docx', 'doc', 'rtf', 'pages', 'odt'].includes(ext) ||
    mime.includes('word') ||
    mime.includes('document')
  ) {
    return 'document';
  }

  if (
    ['py', 'js', 'jsx', 'ts', 'tsx', 'html', 'css', 'json', 'sql', 'sh', 'ps1', 'rs', 'go', 'cpp', 'c', 'h', 'yaml', 'yml'].includes(ext)
  ) {
    return 'code';
  }

  return 'file';
}

/**
 * Returns the human-readable type descriptor matching ChatGPT ("Presentation", "PDF", etc.)
 */
export function getCategorySubtitle(category: FileCategory, fileName: string): string {
  const ext = fileName.split('.').pop()?.toUpperCase();
  switch (category) {
    case 'presentation':
      return 'Presentation';
    case 'pdf':
      return 'PDF';
    case 'spreadsheet':
      return 'Spreadsheet';
    case 'document':
      return 'Document';
    case 'image':
      return 'Image';
    case 'code':
      return ext ? `${ext} File` : 'Code';
    case 'file':
    default:
      return 'File';
  }
}

/**
 * Formats file size in KB or MB cleanly.
 */
export function formatFileSize(bytes: number): string {
  if (!bytes || bytes === 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Renders the ChatGPT-styled 40x40 icon badge for a document card.
 */
export function renderAttachmentBadge(category: FileCategory) {
  switch (category) {
    case 'presentation':
      return (
        <div className="file-badge-icon badge-presentation" title="Presentation">
          <Presentation size={19} className="badge-svg" />
        </div>
      );
    case 'pdf':
      return (
        <div className="file-badge-icon badge-pdf" title="PDF Document">
          <span className="pdf-mark-text">PDF</span>
        </div>
      );
    case 'spreadsheet':
      return (
        <div className="file-badge-icon badge-spreadsheet" title="Spreadsheet">
          <Table size={18} className="badge-svg" />
        </div>
      );
    case 'document':
      return (
        <div className="file-badge-icon badge-document" title="Document">
          <FileText size={18} className="badge-svg" />
        </div>
      );
    case 'code':
      return (
        <div className="file-badge-icon badge-code" title="Code / Script">
          <Code2 size={18} className="badge-svg" />
        </div>
      );
    case 'image':
      return (
        <div className="file-badge-icon badge-image" title="Image">
          <ImageIcon size={18} className="badge-svg" />
        </div>
      );
    case 'file':
    default:
      return (
        <div className="file-badge-icon badge-generic" title="File">
          <File size={18} className="badge-svg" />
        </div>
      );
  }
}
