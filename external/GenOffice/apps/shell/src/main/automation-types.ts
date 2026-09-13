/**
 * Types and interfaces for GenOffice local automation control interface (D7.1).
 */

export type AutomationFormat =
  | 'document'
  | 'presentation'
  | 'spreadsheet'
  | 'pdf'
  | 'markdown'
  | 'html'
  | 'advisory'
  | 'summary'

export type AutomationJobStatus =
  | 'queued'
  | 'generating'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type AutomationAttachmentType =
  | 'image'
  | 'document'
  | 'spreadsheet'
  | 'pdf'
  | 'audio'
  | 'video'

export interface AutomationAttachmentReference {
  type: AutomationAttachmentType
  storage_ref: string
  filename: string
  mime_type?: string
  size_bytes?: number
  metadata?: Record<string, unknown>
}

export const MIN_TIMEOUT_SECONDS = 10
export const DEFAULT_TIMEOUT_SECONDS = 300
export const MAX_TIMEOUT_SECONDS = 1800
export const CANCEL_GRACE_TIMEOUT_MS = 5000

export interface AutomationGenerateOptions {
  title?: string
  approx_pages?: number
  theme?: string
  audience?: string
  tone?: string
  detail_level?: string
  save_directory?: string
  sections_outline?: string[]
  timeout_seconds?: number
  timeout_ms?: number
  max_turns?: number
  custom_metadata?: Record<string, unknown>
}

export interface AutomationGenerateRequest {
  request_id?: string
  job_id?: string
  format: AutomationFormat
  prompt: string
  project_id?: string
  session_id?: string
  canonical_id?: string
  canonical_hash?: string
  options?: AutomationGenerateOptions
  attachments?: AutomationAttachmentReference[]
}

export type AutomationRunnerSubstate =
  | 'STARTING'
  | 'RUNNING_AGENT'
  | 'AGENT_COMPLETED'
  | 'CONTENT_VERIFIED'
  | 'SAVE_STARTED'
  | 'FILE_SAVED'
  | 'FILE_VALIDATED'

export interface AutomationSignal {
  before?: string | number
  after?: string | number
  detail?: string
}

export interface AutomationProgress {
  substate?: AutomationRunnerSubstate
  current_turn: number
  max_turns: number
  last_tool?: string
  message?: string
  content_detected?: boolean
  content_signal?: AutomationSignal
}

export interface AutomationStartAgentPayload {
  job_id: string
  format: AutomationFormat
  instruction: string
  options?: AutomationGenerateOptions
  attachments?: AutomationAttachmentReference[]
}

export interface AutomationProgressPayload {
  job_id: string
  substate?: AutomationRunnerSubstate
  current_turn: number
  max_turns: number
  last_tool?: string
  message?: string
}

export interface AutomationAgentDonePayload {
  job_id: string
  ok: true
  turns: number
  tools_executed: string[]
  content_detected: boolean
  content_signal?: AutomationSignal
}

export interface AutomationAgentErrorPayload {
  job_id: string
  code: string
  message: string
}

export interface AutomationFileSavedPayload {
  job_id: string
  file_path: string
  file_format: string
  title?: string
  metadata?: Record<string, unknown>
}

export interface AutomationArtifact {
  title: string
  file_format: string
  file_path: string
  thumbnail_path?: string
  size_bytes?: number
  content_hash?: string
  metadata?: Record<string, unknown>
}

export interface AutomationOpenRequest {
  file_path: string
}

export interface AutomationOpenResponse {
  ok: true
  opened: boolean
  file_path: string
}

export interface AutomationError {
  code: string
  message: string
  field?: string
  details?: unknown
}

export interface AutomationJobRecord {
  job_id: string
  request_id?: string
  format: AutomationFormat
  prompt: string
  project_id?: string
  session_id?: string
  canonical_id?: string
  canonical_hash?: string
  options?: AutomationGenerateOptions
  attachments?: AutomationAttachmentReference[]
  status: AutomationJobStatus
  created_at: string
  started_at?: string
  completed_at?: string
  cancellation_requested: boolean
  execution_time_seconds?: number
  progress: AutomationProgress | null
  artifact: AutomationArtifact | null
  error: AutomationError | null
}

export interface AutomationDiscoveryMetadata {
  host: string
  port: number
  token: string
  pid: number
  session_id: string
  protocol_version: string
}

export interface AutomationHealthResponse {
  ok: true
  status: 'ready'
  version: string
  pid: number
  protocol_version: string
  uptime_seconds: number
  capabilities: AutomationFormat[]
  active_jobs: number
  queued_jobs: number
}

export interface AutomationRunner {
  (job: AutomationJobRecord): Promise<AutomationArtifact | null>
}
