-- Limo Relational Database Schema (SQLite)
-- ACID-compliant relational storage for core application entities.
-- Foreign keys and WAL mode must be enabled by the connection manager.

-- 1. Projects table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 2. Sources table (raw ingested assets)
-- Note: extracted_text is stored as plain text for prototype storage;
-- advanced vector/indexing is reserved for D5 without premature schema coupling.
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    storage_ref TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    extracted_text TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 3. Chat sessions table
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 4. Messages table (single conversational turns)
-- Strictly public message data; private model chain-of-thought is never stored.
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mode TEXT,
    attachments_json TEXT NOT NULL DEFAULT '[]',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    execution_summary TEXT,
    created_at TEXT NOT NULL
);

-- 5. Transformation jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    session_id TEXT REFERENCES chats(id) ON DELETE SET NULL,
    prompt TEXT,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    requested_formats_json TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0.0,
    current_stage TEXT,
    error TEXT,
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);


-- 6. Canonical content table (structured synthesis intermediate)
CREATE TABLE IF NOT EXISTS canonical_contents (
    id TEXT PRIMARY KEY,
    source_ids_json TEXT NOT NULL,
    title TEXT NOT NULL,
    context TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    entities_json TEXT NOT NULL DEFAULT '[]',
    facts_json TEXT NOT NULL DEFAULT '[]',
    claims_json TEXT NOT NULL DEFAULT '[]',
    events_json TEXT NOT NULL DEFAULT '[]',
    data_points_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    references_json TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 7. Artifacts table (first-class deliverables)
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    file_format TEXT NOT NULL,
    storage_ref TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    description TEXT,
    stats TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    validation_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 8. Artifact versions table (monotonic revision snapshots)
CREATE TABLE IF NOT EXISTS artifact_versions (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    storage_ref TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    change_summary TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_artifact_version UNIQUE (artifact_id, version_number)
);

-- 9. Validation results table (factuality & verification reports)
CREATE TABLE IF NOT EXISTS validation_results (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    is_valid INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL,
    hallucination_check_passed INTEGER NOT NULL DEFAULT 1,
    citations_verified_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]',
    validated_at TEXT NOT NULL
);

-- 10. Provenance records table (tamper-evident cryptographic ledger)
CREATE TABLE IF NOT EXISTS provenance (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    artifact_hash TEXT NOT NULL,
    source_hashes_json TEXT NOT NULL,
    canonical_content_hash TEXT,
    transformation_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    generator_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    signature TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_provenance_artifact_hash UNIQUE (artifact_id, artifact_hash)
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
