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
  | 'pdf'
  | 'sheets'
  | 'video'
  | 'audio'
  | 'image'
  | 'websites'
  | 'code';

export type ModelSpeed = 'Instant' | 'High';

export type FileCategory = 
  | 'presentation' 
  | 'pdf' 
  | 'spreadsheet' 
  | 'document' 
  | 'image' 
  | 'code' 
  | 'file';

export interface AttachmentFile {
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
  previewUrl?: string;
  fileCategory?: FileCategory;
  sourceId?: string;
  uploadStatus?: 'uploading' | 'done' | 'error';
  error?: string;
}

export type ArtifactType = 
  | 'doc' 
  | 'slide' 
  | 'pdf'
  | 'sheet' 
  | 'video' 
  | 'audio'
  | 'infographic'
  | 'website'
  | 'code'
  | 'post';

export interface SocialSlideItem {
  slide_number: number;
  headline: string;
  caption: string;
  visual_suggestion?: string;
}

export interface SocialDraftData {
  platform: 'linkedin' | 'twitter' | 'instagram' | string;
  status: 'Draft';
  title?: string;
  hook?: string;
  body?: string;
  content?: string;
  call_to_action?: string;
  hashtags?: string[];
  tweets?: string[];
  slides?: SocialSlideItem[];
  formatted_text?: string;
  character_count?: number;
}

export interface VoiceOption {
  provider: string;
  voice_id: string;
  display_name: string;
  language: string;
  gender?: string;
  description?: string;
  is_default?: boolean;
  is_available?: boolean;
  is_configured_default?: boolean;
}

export interface VoiceCatalogResponse {
  default_provider: string;
  default_voice: string;
  voices: VoiceOption[];
}

export interface Artifact {
  id: string;
  title: string;
  type: ArtifactType;
  description: string;
  fileFormat: string; // '.docx', '.pptx', '.xlsx', '.mp4', '.html', '.ts', '.md', '.json'
  sizeBytes?: number;
  stats?: string;     // e.g. '12 Slides • 16:9', '4 Pages • 1,840 Words', '1080p • 01:24'
  previewContent?: string;
  sourceCitations?: string[];
  thumbnailUrl?: string;
  metadata?: Record<string, any>;
  mimeType?: string;
  engine?: string;
  skill?: string;
  storagePath?: string;
  sha256?: string;
  version?: number;
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

export interface User {
  id: string;
  provider: string;
  provider_subject?: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  created_at?: string;
  last_login_at?: string;
}
