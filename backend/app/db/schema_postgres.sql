-- Limo Relational Database Schema (PostgreSQL)
-- Explicit schema for Web surface (Supabase / PostgreSQL).
-- Foreign keys and transactional integrity enforced natively.

-- 0. Users table (stable application identity)
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(64) NOT NULL DEFAULT 'google',
    provider_subject VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 0b. User sessions table (secure HTTP-only web sessions)
CREATE TABLE IF NOT EXISTS user_sessions (
    session_token VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 1. Projects table
CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 2. Sources table (raw ingested assets)
CREATE TABLE IF NOT EXISTS sources (
    id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    storage_ref TEXT,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    content_hash VARCHAR(128) NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 3. Chat sessions table
CREATE TABLE IF NOT EXISTS chats (
    id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    mode VARCHAR(64) NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 4. Messages table (single conversational turns)
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    mode VARCHAR(64),
    attachments_json TEXT NOT NULL DEFAULT '[]',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    execution_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Transformation jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL,
    session_id VARCHAR(255) REFERENCES chats(id) ON DELETE SET NULL,
    prompt TEXT,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    requested_formats_json TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'queued',
    progress DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    current_stage VARCHAR(64),
    error TEXT,
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    execution_id VARCHAR(255),
    worker_id VARCHAR(255),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    cancellation_requested BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Canonical content table (structured synthesis intermediate)
CREATE TABLE IF NOT EXISTS canonical_contents (
    id VARCHAR(255) PRIMARY KEY,
    source_ids_json TEXT NOT NULL,
    title VARCHAR(255) NOT NULL,
    context TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    entities_json TEXT NOT NULL DEFAULT '[]',
    facts_json TEXT NOT NULL DEFAULT '[]',
    claims_json TEXT NOT NULL DEFAULT '[]',
    events_json TEXT NOT NULL DEFAULT '[]',
    data_points_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    references_json TEXT NOT NULL DEFAULT '[]',
    content_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 7. Artifacts table (first-class deliverables)
CREATE TABLE IF NOT EXISTS artifacts (
    id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL,
    job_id VARCHAR(255) REFERENCES jobs(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    artifact_type VARCHAR(64) NOT NULL,
    file_format VARCHAR(32) NOT NULL,
    storage_ref TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    content_hash VARCHAR(128) NOT NULL,
    description TEXT,
    stats TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    validation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 8. Artifact versions table (monotonic revision snapshots)
CREATE TABLE IF NOT EXISTS artifact_versions (
    id VARCHAR(255) PRIMARY KEY,
    artifact_id VARCHAR(255) NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    storage_ref TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    content_hash VARCHAR(128) NOT NULL,
    change_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_artifact_version UNIQUE (artifact_id, version_number)
);

-- 9. Validation results table (factuality & verification reports)
CREATE TABLE IF NOT EXISTS validation_results (
    id VARCHAR(255) PRIMARY KEY,
    artifact_id VARCHAR(255) NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    is_valid BOOLEAN NOT NULL DEFAULT FALSE,
    score DOUBLE PRECISION NOT NULL,
    hallucination_check_passed BOOLEAN NOT NULL DEFAULT TRUE,
    citations_verified_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]',
    validated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Provenance records table (tamper-evident cryptographic ledger)
CREATE TABLE IF NOT EXISTS provenance (
    id VARCHAR(255) PRIMARY KEY,
    artifact_id VARCHAR(255) NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    artifact_hash VARCHAR(128) NOT NULL,
    source_hashes_json TEXT NOT NULL,
    canonical_content_hash VARCHAR(128),
    transformation_job_id VARCHAR(255) REFERENCES jobs(id) ON DELETE SET NULL,
    generator_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(128) NOT NULL,
    signature TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_provenance_artifact_hash UNIQUE (artifact_id, artifact_hash)
);

-- 11. Job events table (durable SSE event replay)
CREATE TABLE IF NOT EXISTS job_events (
    event_id VARCHAR(255) PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_job_event_seq UNIQUE (job_id, sequence)
);

-- ============================================================================
-- Performance Indexes for Real Query Patterns
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_sources_project_id ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_chats_project_updated ON chats(project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_jobs_project_created ON jobs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_created ON artifacts(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_versions_artifact_version ON artifact_versions(artifact_id, version_number);
CREATE INDEX IF NOT EXISTS idx_provenance_artifact_created ON provenance(artifact_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_events_job_seq ON job_events(job_id, sequence ASC);
