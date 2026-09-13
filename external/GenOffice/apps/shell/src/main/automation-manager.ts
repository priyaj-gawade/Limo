import { randomUUID } from 'node:crypto'
import type {
  AutomationArtifact,
  AutomationError,
  AutomationGenerateRequest,
  AutomationJobRecord,
  AutomationProgress,
  AutomationRunner,
} from './automation-types'

export interface CancelResultSuccess {
  ok: true
  job_id: string
  status: 'cancelled' | 'generating'
  cancellation_requested?: boolean
  message: string
}

export interface CancelResultFailure {
  ok: false
  status: number
  error: AutomationError
}

export type CancelResult = CancelResultSuccess | CancelResultFailure

export class AutomationJobManager {
  private jobs = new Map<string, AutomationJobRecord>()
  private queue: string[] = []
  private activeJobId: string | null = null
  private runner: AutomationRunner | null = null

  /**
   * Enqueues a validated generation request into the FIFO queue.
   */
  public enqueue(request: AutomationGenerateRequest): AutomationJobRecord {
    const jobId = request.job_id || `job_${randomUUID().replace(/-/g, '')}`
    const now = new Date().toISOString()

    const record: AutomationJobRecord = {
      job_id: jobId,
      request_id: request.request_id,
      format: request.format,
      prompt: request.prompt,
      project_id: request.project_id,
      session_id: request.session_id,
      canonical_id: request.canonical_id,
      canonical_hash: request.canonical_hash,
      options: request.options,
      attachments: request.attachments,
      status: 'queued',
      created_at: now,
      cancellation_requested: false,
      progress: null,
      artifact: null,
      error: null,
    }

    this.jobs.set(jobId, record)
    this.queue.push(jobId)

    // Attempt processing if runner is attached and no active job is running
    this.drainQueue()

    return record
  }

  /**
   * Retrieves a job record by ID.
   */
  public getJob(jobId: string): AutomationJobRecord | undefined {
    return this.jobs.get(jobId)
  }

  /**
   * Returns all known job records.
   */
  public getAllJobs(): AutomationJobRecord[] {
    return Array.from(this.jobs.values())
  }

  public getQueueLength(): number {
    return this.queue.length
  }

  public getActiveCount(): number {
    return this.activeJobId ? 1 : 0
  }

  public getActiveJob(): AutomationJobRecord | undefined {
    return this.activeJobId ? this.jobs.get(this.activeJobId) : undefined
  }

  /**
   * Registers the execution runner callback (implemented in D7.2).
   */
  public setRunner(runner: AutomationRunner | null): void {
    this.runner = runner
    if (runner) {
      this.drainQueue()
    }
  }

  public getRunner(): AutomationRunner | null {
    return this.runner
  }

  /**
   * Cancels a job with strict cancel semantics:
   * - QUEUED: immediately removed from queue, status becomes 'cancelled' (HTTP 200).
   * - GENERATING: sets cancellation_requested = true; D7.2 runner decides termination (HTTP 202).
   * - Terminal states (COMPLETED, FAILED, CANCELLED): returns 409 Conflict.
   * - Not found: returns 404 Not Found.
   */
  public cancel(jobId: string): CancelResult {
    const job = this.jobs.get(jobId)
    if (!job) {
      return {
        ok: false,
        status: 404,
        error: {
          code: 'JOB_NOT_FOUND',
          message: `Job '${jobId}' not found`,
        },
      }
    }

    if (job.status === 'queued') {
      // Dequeue immediately
      const idx = this.queue.indexOf(jobId)
      if (idx !== -1) {
        this.queue.splice(idx, 1)
      }
      job.status = 'cancelled'
      job.completed_at = new Date().toISOString()
      return {
        ok: true,
        job_id: jobId,
        status: 'cancelled',
        message: 'Queued job cancelled before execution',
      }
    }

    if (job.status === 'generating') {
      // Mark cancellation request; D7.2 runner handles loop termination
      job.cancellation_requested = true
      return {
        ok: true,
        job_id: jobId,
        status: 'generating',
        cancellation_requested: true,
        message: 'Cancellation signal registered; awaiting runner termination',
      }
    }

    // Terminal states
    return {
      ok: false,
      status: 409,
      error: {
        code: 'ILLEGAL_STATE_TRANSITION',
        message: `Cannot cancel job in terminal state '${job.status}'`,
      },
    }
  }

  /**
   * Updates progress for an active job (called by D7.2/D7.3 during generation).
   */
  public updateProgress(jobId: string, progress: AutomationProgress): void {
    const job = this.jobs.get(jobId)
    if (job && job.status === 'generating') {
      job.progress = {
        ...(job.progress || {}),
        ...progress,
      }
    }
  }

  /**
   * Completes an active job with the resulting artifact.
   * Invariant: Only 'generating' jobs can transition to 'completed'.
   */
  public completeJob(jobId: string, artifact?: AutomationArtifact | null): void {
    const job = this.jobs.get(jobId)
    if (!job || job.status !== 'generating') return

    job.status = 'completed'
    job.completed_at = new Date().toISOString()
    job.artifact = artifact ?? null
    if (job.started_at) {
      const start = new Date(job.started_at).getTime()
      const end = new Date(job.completed_at).getTime()
      job.execution_time_seconds = Math.max(0, (end - start) / 1000)
    }

    if (this.activeJobId === jobId) {
      this.activeJobId = null
      this.drainQueue()
    }
  }

  /**
   * Fails an active or queued job.
   * Invariant: Only 'generating' jobs can transition to 'failed'.
   */
  public failJob(jobId: string, error: AutomationError): void {
    const job = this.jobs.get(jobId)
    if (!job || job.status !== 'generating') return

    job.status = 'failed'
    job.completed_at = new Date().toISOString()
    job.error = error
    if (job.started_at) {
      const start = new Date(job.started_at).getTime()
      const end = new Date(job.completed_at).getTime()
      job.execution_time_seconds = Math.max(0, (end - start) / 1000)
    }

    if (this.activeJobId === jobId) {
      this.activeJobId = null
      this.drainQueue()
    }
  }

  /**
   * Transitions an active generating job to cancelled once the runner has confirmed termination.
   * Invariant: Only 'generating' jobs can transition to 'cancelled'.
   */
  public finalizeCancellation(jobId: string): void {
    const job = this.jobs.get(jobId)
    if (!job || job.status !== 'generating') return

    job.status = 'cancelled'
    job.completed_at = new Date().toISOString()
    if (job.started_at) {
      const start = new Date(job.started_at).getTime()
      const end = new Date(job.completed_at).getTime()
      job.execution_time_seconds = Math.max(0, (end - start) / 1000)
    }

    if (this.activeJobId === jobId) {
      this.activeJobId = null
      this.drainQueue()
    }
  }

  /**
   * Drains the next job in the queue if runner is attached and no job is generating.
   */
  private drainQueue(): void {
    if (this.activeJobId !== null || !this.runner || this.queue.length === 0) {
      return
    }

    const nextJobId = this.queue.shift()
    if (!nextJobId) return

    const job = this.jobs.get(nextJobId)
    if (!job || job.status !== 'queued') {
      // Skip invalid or already cancelled items
      this.drainQueue()
      return
    }

    this.activeJobId = nextJobId
    job.status = 'generating'
    job.started_at = new Date().toISOString()

    // Invoke runner asynchronously
    Promise.resolve()
      .then(() => this.runner!(job))
      .then((artifact) => {
        if (job.cancellation_requested) {
          this.finalizeCancellation(nextJobId)
        } else {
          this.completeJob(nextJobId, artifact)
        }
      })
      .catch((err) => {
        if (job.cancellation_requested) {
          this.finalizeCancellation(nextJobId)
        } else {
          const errorCode =
            err && typeof err === 'object' && 'code' in err && typeof (err as { code?: unknown }).code === 'string'
              ? (err as { code: string }).code
              : 'EXECUTION_ERROR'
          this.failJob(nextJobId, {
            code: errorCode,
            message: err instanceof Error ? err.message : String(err),
            details: err instanceof Error ? err.stack : undefined,
          })
        }
      })
  }

  /**
   * Resets all internal state (for testing).
   */
  public clear(): void {
    this.jobs.clear()
    this.queue = []
    this.activeJobId = null
    this.runner = null
  }
}

export const automationJobManager = new AutomationJobManager()
