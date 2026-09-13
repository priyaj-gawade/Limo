/**
 * Limo Creation Modes
 * - Core SIH Deliverables: 'docs', 'slides', 'sheets', 'video'
 * - Limo Product Features: 'websites', 'code'
 * - Default: 'none' (Standard conversational AI chat)
 */
export type FeatureMode = 
  | 'none'
  | 'docs'
  | 'slides'
  | 'sheets'
  | 'video'
  | 'websites'
  | 'code';

export type ModelSpeed = 'Instant' | 'High';

export interface AttachmentFile {
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
}

export type ArtifactType = 
  | 'doc' 
  | 'slide' 
  | 'sheet' 
  | 'video' 
  | 'website'
  | 'code';

export interface Artifact {
  id: string;
  title: string;
  type: ArtifactType;
  description: string;
  fileFormat: string; // '.docx', '.pptx', '.xlsx', '.mp4', '.html', '.ts'
  sizeBytes?: number;
  stats?: string;     // e.g. '12 Slides • 16:9', '4 Pages • 1,840 Words', '1080p • 01:24'
  previewContent?: string;
  sourceCitations?: string[];
  thumbnailUrl?: string;
  metadata?: Record<string, any>;
  createdAt: string;
}

export interface ThinkingStep {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'active' | 'completed';
  durationMs?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: FeatureMode;
  attachments?: AttachmentFile[];
  artifactIds?: string[];
  artifacts?: Artifact[];
  executionSummary?: string;
  thinkingSteps?: ThinkingStep[];
  thinkingDurationSec?: number;
  createdAt: string;
}

export interface ChatSession {
  id: string;
  title: string;
  mode: FeatureMode;
  messages: ChatMessage[];
  updatedAt: string;
  createdAt: string;
}
