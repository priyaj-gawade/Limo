import { randomBytes } from 'node:crypto'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { automationJobManager } from './automation-manager'
import type {
  AutomationDiscoveryMetadata,
  AutomationFormat,
  AutomationHealthResponse,
} from './automation-types'
import { parseJsonWithLimit, SUPPORTED_FORMATS, validateGenerateRequest } from './automation-validator'

export const DEFAULT_PORT = 48123
export const PROTOCOL_VERSION = '1.0.0'
export const SHELL_VERSION = '0.9.0'

export interface AutomationServerOptions {
  port?: number
  host?: string
  token?: string
  discoveryDir?: string
}

export class AutomationServer {
  private server: Server | null = null
  private host: string = '127.0.0.1'
  private port: number = DEFAULT_PORT
  private token: string = ''
  private sessionId: string = ''
  private startTime: number = 0
  private discoveryDir: string = join(homedir(), '.genoffice')
  private discoveryFilePath: string = ''
  private isListening: boolean = false
  private documentOpener: ((filePath: string) => boolean) | null = null

  constructor(options?: AutomationServerOptions) {
    if (options?.host) this.host = options.host
    if (options?.port !== undefined) this.port = options.port
    if (options?.discoveryDir) this.discoveryDir = options.discoveryDir
    if (options?.token) this.token = options.token
    this.discoveryFilePath = join(this.discoveryDir, 'automation.json')
  }

  public getPort(): number {
    return this.port
  }

  public getHost(): string {
    return this.host
  }

  public getToken(): string {
    return this.token
  }

  public isRunning(): boolean {
    return this.isListening
  }

  public getDiscoveryFilePath(): string {
    return this.discoveryFilePath
  }

  public setDocumentOpener(opener: (filePath: string) => boolean): void {
    this.documentOpener = opener
  }

  /**
   * Starts the local automation HTTP server and writes the discovery file.
   */
  public async start(): Promise<number> {
    if (this.isListening && this.server) {
      return this.port
    }

    // 1. Generate cryptographically random token if not preset
    if (!this.token) {
      this.token = randomBytes(32).toString('hex')
    }

    this.sessionId = `sess_${Date.now()}_${process.pid}`
    this.startTime = Date.now()

    return new Promise<number>((resolve, reject) => {
      const tryListen = (portToTry: number, isFallback: boolean) => {
        const srv = createServer((req, res) => {
          this.handleRequest(req, res).catch((err) => {
            this.sendJson(res, 500, {
              ok: false,
              error: {
                code: 'INTERNAL_SERVER_ERROR',
                message: err instanceof Error ? err.message : String(err),
              },
            })
          })
        })

        this.server = srv

        srv.on('error', (err: NodeJS.ErrnoException) => {
          if (err.code === 'EADDRINUSE' && !isFallback && portToTry !== 0) {
            // Preferred port occupied -> fall back to an available localhost port (port 0)
            tryListen(0, true)
          } else {
            reject(err)
          }
        })

        srv.listen(portToTry, this.host, () => {
          const addr = srv.address()
          if (addr && typeof addr === 'object') {
            this.port = addr.port
          }
          this.isListening = true
          this.writeDiscoveryFile()
          resolve(this.port)
        })
      }

      tryListen(this.port, false)
    })
  }

  /**
   * Stops the server and removes the local discovery file.
   */
  public async stop(): Promise<void> {
    this.removeDiscoveryFile()
    if (!this.server) {
      this.isListening = false
      return
    }

    return new Promise<void>((resolve) => {
      this.server!.close(() => {
        this.server = null
        this.isListening = false
        resolve()
      })
    })
  }

  /**
   * Writes ~/.genoffice/automation.json with mode 0o600.
   */
  private writeDiscoveryFile(): void {
    try {
      if (!existsSync(this.discoveryDir)) {
        mkdirSync(this.discoveryDir, { recursive: true, mode: 0o700 })
      }

      const metadata: AutomationDiscoveryMetadata = {
        host: this.host,
        port: this.port,
        token: this.token,
        pid: process.pid,
        session_id: this.sessionId,
        protocol_version: PROTOCOL_VERSION,
      }

      writeFileSync(this.discoveryFilePath, JSON.stringify(metadata, null, 2), {
        encoding: 'utf8',
        mode: 0o600,
      })
    } catch (err) {
      console.error('[GenOffice Automation] Failed to write discovery file:', err)
    }
  }

  /**
   * Removes discovery file on exit.
   */
  private removeDiscoveryFile(): void {
    try {
      if (existsSync(this.discoveryFilePath)) {
        rmSync(this.discoveryFilePath, { force: true })
      }
    } catch {
      // Ignore cleanup error on process exit
    }
  }

  /**
   * Main HTTP request router.
   */
  private async handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
    // 1. Host header validation (defense-in-depth rebinding protection)
    const hostHeader = req.headers.host || ''
    const validHostPattern = /^(127\.0\.0\.1|localhost)(:\d+)?$/i
    if (!validHostPattern.test(hostHeader)) {
      this.sendJson(res, 403, {
        ok: false,
        error: {
          code: 'FORBIDDEN_HOST',
          message: `Invalid Host header '${hostHeader}'. Loopback requests only.`,
        },
      })
      return
    }

    const url = new URL(req.url || '/', `http://${this.host}:${this.port}`)
    const pathname = url.pathname

    // 2. Health endpoint (no auth token required from loopback)
    if (pathname === '/api/v1/health' || pathname === '/health') {
      if (req.method !== 'GET') {
        this.sendJson(res, 405, { ok: false, error: { code: 'METHOD_NOT_ALLOWED', message: 'Use GET' } })
        return
      }
      this.handleHealth(res)
      return
    }

    // 3. Authenticate all other endpoints via X-GenOffice-Token or Bearer header
    if (!this.authenticate(req)) {
      this.sendJson(res, 401, {
        ok: false,
        error: {
          code: 'UNAUTHORIZED',
          message: 'Missing or invalid authentication token. Provide X-GenOffice-Token header.',
        },
      })
      return
    }

    // 4. Route matching
    // POST /api/v1/generate or aliases
    if (
      pathname === '/api/v1/generate' ||
      pathname === '/api/v1/genoffice/docs' ||
      pathname === '/api/v1/genoffice/slides' ||
      pathname === '/api/v1/genoffice/sheets'
    ) {
      if (req.method !== 'POST') {
        this.sendJson(res, 405, { ok: false, error: { code: 'METHOD_NOT_ALLOWED', message: 'Use POST' } })
        return
      }

      let defaultFormat: AutomationFormat | undefined
      if (pathname.endsWith('/docs')) defaultFormat = 'document'
      else if (pathname.endsWith('/slides')) defaultFormat = 'presentation'
      else if (pathname.endsWith('/sheets')) defaultFormat = 'spreadsheet'

      await this.handleGenerate(req, res, defaultFormat)
      return
    }

    // Match /api/v1/jobs/:job_id/cancel
    const cancelMatch = pathname.match(/^\/api\/v1\/jobs\/([a-zA-Z0-9_-]+)\/cancel\/?$/)
    if (cancelMatch) {
      if (req.method !== 'POST') {
        this.sendJson(res, 405, { ok: false, error: { code: 'METHOD_NOT_ALLOWED', message: 'Use POST' } })
        return
      }
      const jobId = cancelMatch[1]
      this.handleCancel(jobId, res)
      return
    }

    // Match /api/v1/jobs/:job_id
    const jobMatch = pathname.match(/^\/api\/v1\/jobs\/([a-zA-Z0-9_-]+)\/?$/)
    if (jobMatch) {
      if (req.method !== 'GET') {
        this.sendJson(res, 405, { ok: false, error: { code: 'METHOD_NOT_ALLOWED', message: 'Use GET' } })
        return
      }
      const jobId = jobMatch[1]
      this.handleGetJob(jobId, res)
      return
    }

    // Match /api/v1/open
    if (pathname === '/api/v1/open') {
      if (req.method !== 'POST') {
        this.sendJson(res, 405, { ok: false, error: { code: 'METHOD_NOT_ALLOWED', message: 'Use POST' } })
        return
      }
      await this.handleOpen(req, res)
      return
    }

    // Unknown route
    this.sendJson(res, 404, {
      ok: false,
      error: {
        code: 'NOT_FOUND',
        message: `Endpoint '${pathname}' not found`,
      },
    })
  }

  /**
   * Validates token from headers without logging the secret.
   */
  private authenticate(req: IncomingMessage): boolean {
    const rawHeader = req.headers['x-genoffice-token'] || req.headers['authorization']
    if (!rawHeader) return false

    const headerStr = Array.isArray(rawHeader) ? rawHeader[0] : rawHeader
    const token = headerStr.startsWith('Bearer ') ? headerStr.slice(7).trim() : headerStr.trim()

    return token.length > 0 && token === this.token
  }

  /**
   * GET /api/v1/health
   */
  private handleHealth(res: ServerResponse): void {
    const uptimeSeconds = (Date.now() - this.startTime) / 1000
    const health: AutomationHealthResponse = {
      ok: true,
      status: 'ready',
      version: SHELL_VERSION,
      pid: process.pid,
      protocol_version: PROTOCOL_VERSION,
      uptime_seconds: Math.round(uptimeSeconds * 10) / 10,
      capabilities: Array.from(SUPPORTED_FORMATS),
      active_jobs: automationJobManager.getActiveCount(),
      queued_jobs: automationJobManager.getQueueLength(),
    }

    this.sendJson(res, 200, health)
  }

  /**
   * POST /api/v1/generate
   */
  private async handleGenerate(
    req: IncomingMessage,
    res: ServerResponse,
    defaultFormat?: AutomationFormat,
  ): Promise<void> {
    const bodyResult = await parseJsonWithLimit(req)
    if (!bodyResult.ok) {
      this.sendJson(res, bodyResult.status, { ok: false, error: bodyResult.error })
      return
    }

    const rawPayload = bodyResult.value as Record<string, unknown>
    if (defaultFormat && !rawPayload.format && !rawPayload.type) {
      rawPayload.format = defaultFormat
    }

    const validation = validateGenerateRequest(rawPayload)
    if (!validation.ok) {
      this.sendJson(res, validation.status, { ok: false, error: validation.error })
      return
    }

    const job = automationJobManager.enqueue(validation.value)

    this.sendJson(res, 202, {
      ok: true,
      job_id: job.job_id,
      status: job.status,
      format: job.format,
      created_at: job.created_at,
      poll_url: `/api/v1/jobs/${job.job_id}`,
    })
  }

  /**
   * GET /api/v1/jobs/:job_id
   */
  private handleGetJob(jobId: string, res: ServerResponse): void {
    const job = automationJobManager.getJob(jobId)
    if (!job) {
      this.sendJson(res, 404, {
        ok: false,
        error: {
          code: 'JOB_NOT_FOUND',
          message: `Job '${jobId}' not found`,
        },
      })
      return
    }

    this.sendJson(res, 200, {
      ok: true,
      job_id: job.job_id,
      status: job.status,
      format: job.format,
      created_at: job.created_at,
      started_at: job.started_at ?? null,
      completed_at: job.completed_at ?? null,
      cancellation_requested: job.cancellation_requested,
      execution_time_seconds: job.execution_time_seconds ?? null,
      progress: job.progress,
      artifact: job.artifact,
      error: job.error,
      attachments: job.attachments ?? [],
    })
  }

  /**
   * POST /api/v1/jobs/:job_id/cancel
   */
  private handleCancel(jobId: string, res: ServerResponse): void {
    const result = automationJobManager.cancel(jobId)
    if (!result.ok) {
      this.sendJson(res, result.status, { ok: false, error: result.error })
      return
    }

    if (result.status === 'cancelled') {
      this.sendJson(res, 200, result)
    } else {
      // 'generating' cancellation signal accepted
      this.sendJson(res, 202, result)
    }
  }

  /**
   * POST /api/v1/open
   */
  private async handleOpen(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const bodyResult = await parseJsonWithLimit(req)
    if (!bodyResult.ok) {
      this.sendJson(res, bodyResult.status, { ok: false, error: bodyResult.error })
      return
    }

    const payload = bodyResult.value as Record<string, unknown>
    const filePath = typeof payload.file_path === 'string' ? payload.file_path.trim() : ''
    if (!filePath) {
      this.sendJson(res, 400, {
        ok: false,
        error: {
          code: 'INVALID_REQUEST',
          message: 'file_path must be a non-empty string',
        },
      })
      return
    }

    if (!existsSync(filePath)) {
      this.sendJson(res, 404, {
        ok: false,
        error: {
          code: 'FILE_NOT_FOUND',
          message: `File '${filePath}' not found on disk`,
        },
      })
      return
    }

    let opened = false
    if (this.documentOpener) {
      try {
        opened = this.documentOpener(filePath)
      } catch (err) {
        console.error('[AutomationServer] Document opener threw error:', err)
      }
    }

    this.sendJson(res, 200, {
      ok: true,
      opened,
      file_path: filePath,
    })
  }

  /**
   * Sends JSON HTTP response with headers.
   */
  private sendJson(res: ServerResponse, statusCode: number, data: unknown): void {
    const body = JSON.stringify(data)
    res.writeHead(statusCode, {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
      'Cache-Control': 'no-store',
      Connection: 'close',
    })
    res.end(body)
  }
}

export const automationServer = new AutomationServer()
