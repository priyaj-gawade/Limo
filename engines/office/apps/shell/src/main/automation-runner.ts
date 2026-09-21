import { existsSync, unlinkSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import { ipcMain } from 'electron'
import type { BrowserWindow, IpcMainEvent } from 'electron'
import { validateSavedDocument } from './automation-file-validator'
import type { AutomationJobManager } from './automation-manager'
import {
  DEFAULT_TIMEOUT_SECONDS,
  type AutomationAgentDonePayload,
  type AutomationAgentErrorPayload,
  type AutomationArtifact,
  type AutomationFileSavedPayload,
  type AutomationJobRecord,
  type AutomationProgressPayload,
  type AutomationRunner,
  type AutomationStartAgentPayload,
} from './automation-types'
import type { AutomationViewManager } from './automation-view-manager'

const RENDERER_READY_TIMEOUT_MS = 15_000

export class AutomationExecutionRunner {
  private activeJobId: string | null = null
  private pendingReadyResolvers = new Map<number, () => void>()
  private readyWcIds = new Set<number>()
  private activeDoneResolver: ((value: AutomationAgentDonePayload) => void) | null = null
  private activeFileSavedResolver: ((value: AutomationFileSavedPayload) => void) | null = null
  private activeErrorResolver: ((error: Error) => void) | null = null
  private pendingDonePayload: AutomationAgentDonePayload | null = null
  private pendingFileSavedPayload: AutomationFileSavedPayload | null = null
  private pendingErrorPayload: Error | null = null

  constructor(
    private readonly viewManager: AutomationViewManager,
    private readonly jobManager: AutomationJobManager,
    private readonly shellWindow: BrowserWindow,
  ) {
    this.registerIpc()
  }

  private registerIpc(): void {
    // 1. Renderer ready signal
    ipcMain.on('automation:renderer-ready', (event: IpcMainEvent, _payload: { format: string }) => {
      const resolver = this.pendingReadyResolvers.get(event.sender.id)
      if (resolver) {
        this.pendingReadyResolvers.delete(event.sender.id)
        resolver()
      } else {
        this.readyWcIds.add(event.sender.id)
      }
    })

    // 2. Renderer progress signal
    ipcMain.on('automation:agent-progress', (_event: IpcMainEvent, payload: AutomationProgressPayload) => {
      if (this.activeJobId && payload.job_id === this.activeJobId) {
        this.jobManager.updateProgress(this.activeJobId, {
          substate: 'RUNNING_AGENT',
          current_turn: payload.current_turn,
          max_turns: payload.max_turns || 100,
          last_tool: payload.last_tool,
          message: payload.message,
        })
      }
    })

    // 3. Renderer done signal
    ipcMain.on('automation:agent-done', (_event: IpcMainEvent, payload: AutomationAgentDonePayload) => {
      if (this.activeJobId && payload.job_id === this.activeJobId) {
        if (this.activeDoneResolver) {
          const resolve = this.activeDoneResolver
          this.activeDoneResolver = null
          this.activeErrorResolver = null
          resolve(payload)
        } else {
          this.pendingDonePayload = payload
        }
      }
    })

    // 4. Renderer error signal
    ipcMain.on('automation:agent-error', (_event: IpcMainEvent, payload: AutomationAgentErrorPayload) => {
      if (this.activeJobId && payload.job_id === this.activeJobId) {
        const err = new Error(payload.message)
        ;(err as unknown as { code?: string }).code = payload.code
        if (this.activeErrorResolver) {
          const reject = this.activeErrorResolver
          this.activeDoneResolver = null
          this.activeFileSavedResolver = null
          this.activeErrorResolver = null
          reject(err)
        } else {
          this.pendingErrorPayload = err
        }
      }
    })

    // 5. Renderer cancelled signal
    ipcMain.on('automation:agent-cancelled', (_event: IpcMainEvent, payload: { job_id: string }) => {
      if (this.activeJobId && payload.job_id === this.activeJobId) {
        if (this.activeDoneResolver) {
          const resolve = this.activeDoneResolver
          this.activeDoneResolver = null
          this.activeFileSavedResolver = null
          this.activeErrorResolver = null
          resolve({
            job_id: payload.job_id,
            ok: true,
            turns: 0,
            tools_executed: [],
            content_detected: false,
          })
        }
      }
    })

    // 6. Renderer file-saved signal (D7.4)
    ipcMain.on('automation:file-saved', (_event: IpcMainEvent, payload: AutomationFileSavedPayload) => {
      if (this.activeJobId && payload.job_id === this.activeJobId) {
        if (this.activeFileSavedResolver) {
          const resolve = this.activeFileSavedResolver
          this.activeFileSavedResolver = null
          resolve(payload)
        } else {
          this.pendingFileSavedPayload = payload
        }
      }
    })
  }

  /**
   * Returns the AutomationRunner function registered with AutomationJobManager.setRunner.
   */
  public getRunner(): AutomationRunner {
    return (job: AutomationJobRecord) => this.execute(job)
  }

  /**
   * Executes a single automation job.
   */
  public async execute(job: AutomationJobRecord): Promise<AutomationArtifact | null> {
    this.activeJobId = job.job_id

    // Check cancellation immediately
    if (job.cancellation_requested) {
      this.activeJobId = null
      return null
    }
    const maxTurns = job.options?.max_turns ?? 100
    const timeoutMs = job.options?.timeout_ms ?? ((job.options?.timeout_seconds ?? DEFAULT_TIMEOUT_SECONDS) * 1000)

    // 1. STARTING: Allocate hidden background WebContentsView
    this.jobManager.updateProgress(job.job_id, {
      substate: 'STARTING',
      current_turn: 0,
      max_turns: maxTurns,
      message: `Initializing hidden background view for ${job.format}`,
    })

    let handle
    try {
      handle = await this.viewManager.createHiddenView(job.format, job.options?.title)
    } catch (err) {
      this.activeJobId = null
      throw err
    }

    const wcId = handle.webContentsId
    const wc = handle.view.webContents

    let cancelCheckInterval: NodeJS.Timeout | null = null
    let hardTimeoutTimer: NodeJS.Timeout | null = null
    let graceTimeoutTimer: NodeJS.Timeout | null = null
    let cancellationStartTime: number | null = null

    const onRenderProcessGone = (_e: unknown, details: { reason: string; exitCode: number }) => {
      console.error(`[AutomationExecutionRunner] Render process gone: ${details.reason} (exitCode: ${details.exitCode})`)
      const err = new Error(`RENDERER_PROCESS_GONE: Process terminated (${details.reason}, exitCode: ${details.exitCode})`)
      ;(err as unknown as { code?: string }).code = 'RENDERER_PROCESS_GONE'
      if (this.activeErrorResolver) {
        const reject = this.activeErrorResolver
        this.activeDoneResolver = null
        this.activeErrorResolver = null
        reject(err)
      } else {
        this.pendingErrorPayload = err
      }
    }

    const onUnresponsive = () => {
      console.warn(`[AutomationExecutionRunner] webContents ${wcId} became unresponsive`)
      this.jobManager.updateProgress(job.job_id, {
        substate: 'RUNNING_AGENT',
        current_turn: 0,
        max_turns: maxTurns,
        message: 'Renderer process is temporarily unresponsive; awaiting cycle',
      })
    }

    try {
      if (typeof wc.on === 'function') {
        wc.once('render-process-gone', onRenderProcessGone)
        wc.on('unresponsive', onUnresponsive)
      }

      // 2. Await renderer ready handshake (or consume buffered ready)
      if (this.readyWcIds.has(wcId)) {
        this.readyWcIds.delete(wcId)
      } else {
        await new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => {
            this.pendingReadyResolvers.delete(wcId)
            reject(new Error(`RENDERER_INIT_TIMEOUT: Renderer did not signal ready within ${RENDERER_READY_TIMEOUT_MS}ms`))
          }, RENDERER_READY_TIMEOUT_MS)

          this.pendingReadyResolvers.set(wcId, () => {
            clearTimeout(timeout)
            resolve()
          })
        })
      }

      // Check cancellation again before launching agent
      if (job.cancellation_requested) {
        return null
      }

      // 3. Verify attachment references on local disk
      if (job.attachments && job.attachments.length > 0) {
        for (const att of job.attachments) {
          if (!att.storage_ref || !existsSync(att.storage_ref)) {
            const err = new Error(`ATTACHMENT_UNREADABLE: Local file not found: '${att.filename}' at '${att.storage_ref}'`)
            ;(err as unknown as { code?: string }).code = 'ATTACHMENT_UNREADABLE'
            throw err
          }
        }
      }

      // 4. RUNNING_AGENT: Dispatch instruction to renderer
      this.jobManager.updateProgress(job.job_id, {
        substate: 'RUNNING_AGENT',
        current_turn: 0,
        max_turns: maxTurns,
        message: 'Starting native AgentLoop',
      })

      const startPayload: AutomationStartAgentPayload = {
        job_id: job.job_id,
        format: job.format,
        instruction: job.prompt,
        options: job.options,
        attachments: job.attachments,
      }

      wc.send('automation:start-agent', startPayload)

      // 5. Multi-stage timeout escalation
      let timedOut = false
      hardTimeoutTimer = setTimeout(() => {
        timedOut = true
        console.warn(`[AutomationExecutionRunner] Job ${job.job_id} exceeded execution timeout of ${timeoutMs}ms. Escalating cancellation.`)
        this.jobManager.updateProgress(job.job_id, {
          substate: 'RUNNING_AGENT',
          current_turn: 0,
          max_turns: maxTurns,
          message: `Execution exceeded timeout (${timeoutMs}ms); initiating cooperative cancellation`,
        })

        if (!wc.isDestroyed()) {
          wc.send('automation:agent-cancel', { job_id: job.job_id, reason: 'EXECUTION_TIMEOUT' })
        }

        // Grace period for cooperative shutdown before force-terminating
        graceTimeoutTimer = setTimeout(() => {
          console.error(`[AutomationExecutionRunner] Job ${job.job_id} failed to exit within grace period after timeout. Force-killing view.`)
          const err = new Error(`EXECUTION_TIMEOUT: Job exceeded maximum execution time of ${timeoutMs}ms`)
          ;(err as unknown as { code?: string }).code = 'EXECUTION_TIMEOUT'
          if (this.activeErrorResolver) {
            const reject = this.activeErrorResolver
            this.activeDoneResolver = null
            this.activeErrorResolver = null
            reject(err)
          } else {
            this.pendingErrorPayload = err
          }
        }, 5000)
        if (graceTimeoutTimer.unref) graceTimeoutTimer.unref()
      }, timeoutMs)
      if (hardTimeoutTimer.unref) hardTimeoutTimer.unref()

      // 6. Watch for cancellation while running with escalation
      cancelCheckInterval = setInterval(() => {
        if (job.cancellation_requested) {
          if (!cancellationStartTime) {
            cancellationStartTime = Date.now()
          }

          if (!wc.isDestroyed()) {
            wc.send('automation:agent-cancel', { job_id: job.job_id })
          }

          // If cancellation has been pending for > 10,000ms without renderer response, force abort
          if (Date.now() - cancellationStartTime > 10000) {
            console.warn(`[AutomationExecutionRunner] Job ${job.job_id} cancellation pending > 10s. Force-aborting view.`)
            if (this.activeDoneResolver) {
              const resolve = this.activeDoneResolver
              this.activeDoneResolver = null
              this.activeErrorResolver = null
              resolve({
                job_id: job.job_id,
                ok: true,
                turns: 0,
                tools_executed: [],
                content_detected: false,
              })
            }
          }
        }
      }, 200)
      if (cancelCheckInterval.unref) cancelCheckInterval.unref()

      // 7. Await completion or error from renderer
      let doneResult: AutomationAgentDonePayload
      if (this.pendingDonePayload) {
        doneResult = this.pendingDonePayload
        this.pendingDonePayload = null
      } else if (this.pendingErrorPayload) {
        const err = this.pendingErrorPayload
        this.pendingErrorPayload = null
        throw err
      } else {
        doneResult = await new Promise<AutomationAgentDonePayload>((resolve, reject) => {
          this.activeDoneResolver = resolve
          this.activeErrorResolver = reject
        })
      }

      // 8. Check if timed out or cancelled before finishing
      if (timedOut) {
        const err = new Error(`EXECUTION_TIMEOUT: Job exceeded maximum execution time of ${timeoutMs}ms`)
        ;(err as unknown as { code?: string }).code = 'EXECUTION_TIMEOUT'
        throw err
      }

      if (job.cancellation_requested) {
        return null
      }

      // 9. AGENT_COMPLETED
      this.jobManager.updateProgress(job.job_id, {
        substate: 'AGENT_COMPLETED',
        current_turn: doneResult.turns,
        max_turns: maxTurns,
        content_detected: doneResult.content_detected,
        content_signal: doneResult.content_signal,
        message: `AgentLoop completed (${doneResult.tools_executed.join(', ') || 'no tools'}; content_detected: ${doneResult.content_detected})`,
      })

      // 10. CONTENT_VERIFIED: Verify content was generated
      if (!doneResult.content_detected) {
        const detailMsg = typeof doneResult.content_signal === 'object' ? JSON.stringify(doneResult.content_signal) : doneResult.content_signal
        const err = new Error(`ZERO_CONTENT_GENERATED: AgentLoop completed without generating detectable content (${detailMsg || 'none'})`)
        ;(err as unknown as { code?: string }).code = 'ZERO_CONTENT_GENERATED'
        throw err
      }

      this.jobManager.updateProgress(job.job_id, {
        substate: 'CONTENT_VERIFIED',
        current_turn: doneResult.turns,
        max_turns: maxTurns,
        content_detected: true,
        content_signal: doneResult.content_signal,
        message: `Document content verified (${doneResult.content_signal || 'content present'})`,
      })

      // 11. SAVE_STARTED: Await native save resolution from renderer
      this.jobManager.updateProgress(job.job_id, {
        substate: 'SAVE_STARTED',
        current_turn: doneResult.turns,
        max_turns: maxTurns,
        content_detected: true,
        content_signal: doneResult.content_signal,
        message: 'Awaiting native document save completion',
      })

      let fileSaved: AutomationFileSavedPayload
      if (this.pendingFileSavedPayload) {
        fileSaved = this.pendingFileSavedPayload
        this.pendingFileSavedPayload = null
      } else if (this.pendingErrorPayload) {
        const err = this.pendingErrorPayload
        this.pendingErrorPayload = null
        throw err
      } else {
        fileSaved = await new Promise<AutomationFileSavedPayload>((resolve, reject) => {
          this.activeFileSavedResolver = resolve
          this.activeErrorResolver = reject
        })
      }

      if (timedOut) {
        const err = new Error(`EXECUTION_TIMEOUT: Job exceeded maximum execution time of ${timeoutMs}ms`)
        ;(err as unknown as { code?: string }).code = 'EXECUTION_TIMEOUT'
        throw err
      }

      if (job.cancellation_requested) {
        return null
      }

      // 12. FILE_SAVED: Confirm file exists on local filesystem
      if (!existsSync(fileSaved.file_path)) {
        const err = new Error(`FILE_NOT_FOUND_AFTER_SAVE: Saved file not found at '${fileSaved.file_path}'`)
        ;(err as unknown as { code?: string }).code = 'FILE_NOT_FOUND_AFTER_SAVE'
        throw err
      }

      this.jobManager.updateProgress(job.job_id, {
        substate: 'FILE_SAVED',
        current_turn: doneResult.turns,
        max_turns: maxTurns,
        content_detected: true,
        content_signal: doneResult.content_signal,
        message: `Native save completed (${fileSaved.file_path})`,
      })

      // 13. FILE_VALIDATED: Structural validation (OpenXML / pdf-lib + SHA-256)
      const valResult = await validateSavedDocument(fileSaved.file_path, job.format)
      if (!valResult.valid) {
        try {
          if (existsSync(fileSaved.file_path)) unlinkSync(fileSaved.file_path)
        } catch {
          /* fail-safe corrupt cleanup */
        }
        const err = new Error(`CORRUPT_FILE_GENERATED: Structural validation failed: ${valResult.error}`)
        ;(err as unknown as { code?: string }).code = 'CORRUPT_FILE_GENERATED'
        throw err
      }

      // Mark backing file as committed
      handle.fileCommitted = true

      // If standalone creation occurred (PDF Pathway B or in-memory Spreadsheet export), unlink the unused initial blank backing file
      if (
        (job.format === 'pdf' || job.format === 'spreadsheet') &&
        handle.backingFilePath &&
        handle.backingFilePath !== fileSaved.file_path
      ) {
        try {
          if (existsSync(handle.backingFilePath)) {
            unlinkSync(handle.backingFilePath)
            console.log(`[AutomationExecutionRunner] Unlinked unused blank backing ${job.format}: ${handle.backingFilePath}`)
          }
        } catch (err) {
          console.warn(`[AutomationExecutionRunner] Failed to unlink unused backing ${job.format}: ${handle.backingFilePath}`, err)
        }
      }

      this.jobManager.updateProgress(job.job_id, {
        substate: 'FILE_VALIDATED',
        current_turn: doneResult.turns,
        max_turns: maxTurns,
        content_detected: true,
        content_signal: doneResult.content_signal,
        message: `File integrity validated (${valResult.size_bytes} bytes, sha256: ${valResult.sha256.slice(0, 8)}...)`,
      })

      // 13.5 Capture real rendered thumbnail from mounted WebContentsView before teardown
      let thumbnailPath: string | undefined
      try {
        if (typeof wc.capturePage === 'function') {
          if (handle?.view && typeof handle.view.setVisible === 'function') {
            handle.view.setVisible(true)
          }
          if (job.format === 'pdf' && fileSaved.file_path && handle.backingFilePath !== fileSaved.file_path) {
            try {
              await wc.loadURL(`file://${fileSaved.file_path.replace(/\\/g, '/')}`)
              await new Promise((r) => setTimeout(r, 500))
            } catch {
              /* ignore */
            }
          }
          const image = await Promise.race([
            wc.capturePage(),
            new Promise<null>((r) => setTimeout(() => r(null), 2500)),
          ])
          console.log(`[AutomationExecutionRunner] capturePage result: size=${JSON.stringify(image?.getSize?.())}, isEmpty=${image?.isEmpty?.()}`)
          if (handle?.view && typeof handle.view.setVisible === 'function') {
            handle.view.setVisible(false)
          }
          if (image && typeof image.isEmpty === 'function' && !image.isEmpty()) {
            const size = image.getSize()
            const targetWidth = 480
            const targetHeight = size.width > 0 ? Math.round((size.height / size.width) * targetWidth) : 300
            const resized = typeof image.resize === 'function'
              ? image.resize({ width: targetWidth, height: targetHeight, quality: 'better' })
              : image
            const thumbBuffer = resized.toPNG()
            thumbnailPath = `${fileSaved.file_path}.thumb.png`
            writeFileSync(thumbnailPath, thumbBuffer)
            console.log(`[AutomationExecutionRunner] Captured real thumbnail (${thumbBuffer.length} bytes): ${thumbnailPath}`)
          }
        }
      } catch (thumbErr) {
        console.warn('[AutomationExecutionRunner] Non-fatal thumbnail capture error:', thumbErr)
      }

      // 14. Construct authoritative GenOffice-side AutomationArtifact
      const artifact: AutomationArtifact = {
        title: fileSaved.title || job.options?.title || basename(fileSaved.file_path),
        file_format: job.format,
        file_path: fileSaved.file_path,
        thumbnail_path: thumbnailPath,
        size_bytes: valResult.size_bytes,
        content_hash: valResult.sha256,
        metadata: {
          ...(fileSaved.metadata || {}),
          ...(valResult.metadata || {}),
          thumbnail_path: thumbnailPath,
          file_name: basename(fileSaved.file_path),
          created_at: new Date().toISOString(),
        },
      }

      return artifact
    } finally {
      if (hardTimeoutTimer) clearTimeout(hardTimeoutTimer)
      if (graceTimeoutTimer) clearTimeout(graceTimeoutTimer)
      if (cancelCheckInterval) clearInterval(cancelCheckInterval)

      if (typeof wc.removeListener === 'function') {
        try {
          wc.removeListener('render-process-gone', onRenderProcessGone)
          wc.removeListener('unresponsive', onUnresponsive)
        } catch {
          /* fail-safe */
        }
      }

      this.activeJobId = null
      this.activeDoneResolver = null
      this.activeFileSavedResolver = null
      this.activeErrorResolver = null
      this.pendingDonePayload = null
      this.pendingFileSavedPayload = null
      this.pendingErrorPayload = null
      this.pendingReadyResolvers.delete(wcId)
      this.readyWcIds.delete(wcId)
      this.viewManager.destroyActiveView()
    }
  }
}
