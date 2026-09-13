import { existsSync, readFileSync, rmSync } from 'node:fs'
import { createServer, request as httpRequest } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { automationJobManager } from '../src/main/automation-manager'
import { AutomationServer } from '../src/main/automation-server'
import type { AutomationArtifact } from '../src/main/automation-types'

describe('GenOffice Local Automation Interface (D7.1)', () => {
  let server: AutomationServer
  let port: number
  let testDir: string
  let token: string

  const request = (
    method: string,
    path: string,
    headers: Record<string, string> = {},
    body?: string | Buffer,
  ): Promise<{ status: number; headers: Record<string, string | string[] | undefined>; data: any }> => {
    return new Promise((resolve, reject) => {
      const defaultHeaders: Record<string, string> = {
        Host: `127.0.0.1:${port}`,
        ...headers,
      }

      const req = httpRequest(
        {
          hostname: '127.0.0.1',
          port,
          path,
          method,
          headers: defaultHeaders,
        },
        (res) => {
          const chunks: Buffer[] = []
          res.on('data', (c) => chunks.push(c))
          res.on('end', () => {
            const raw = Buffer.concat(chunks).toString('utf8')
            let parsed: any = raw
            try {
              parsed = JSON.parse(raw)
            } catch {
              // raw string
            }
            resolve({
              status: res.statusCode || 0,
              headers: res.headers,
              data: parsed,
            })
          })
        },
      )

      req.on('error', reject)
      if (body) {
        req.write(body)
      }
      req.end()
    })
  }

  beforeEach(async () => {
    automationJobManager.clear()
    testDir = join(tmpdir(), `genoffice-auto-test-${Date.now()}-${Math.random().toString(36).slice(2)}`)
    server = new AutomationServer({
      port: 0, // ephemeral port for test isolation
      discoveryDir: testDir,
    })
    port = await server.start()
    token = server.getToken()
  })

  afterEach(async () => {
    await server.stop()
    automationJobManager.clear()
    if (existsSync(testDir)) {
      rmSync(testDir, { recursive: true, force: true })
    }
  })

  describe('Discovery File & Token Security (Must-Fix #2 & #6)', () => {
    it('creates discovery file with strictly connection metadata and user permissions', () => {
      const discoveryPath = server.getDiscoveryFilePath()
      expect(existsSync(discoveryPath)).toBe(true)

      const raw = readFileSync(discoveryPath, 'utf8')
      const data = JSON.parse(raw)

      // Strict metadata only
      expect(data).toHaveProperty('host', '127.0.0.1')
      expect(data).toHaveProperty('port', port)
      expect(data).toHaveProperty('token', token)
      expect(data).toHaveProperty('pid', process.pid)
      expect(data).toHaveProperty('protocol_version', '1.0.0')
      expect(data).toHaveProperty('session_id')

      // Must NOT contain job or artifact state
      expect(data).not.toHaveProperty('jobs')
      expect(data).not.toHaveProperty('queue')
      expect(data).not.toHaveProperty('artifacts')

      // Token must be cryptographically random hex (32 bytes = 64 hex chars)
      expect(token).toMatch(/^[a-f0-9]{64}$/)
    })

    it('unlinks discovery file upon server stop', async () => {
      const discoveryPath = server.getDiscoveryFilePath()
      expect(existsSync(discoveryPath)).toBe(true)

      await server.stop()
      expect(existsSync(discoveryPath)).toBe(false)
    })

    it('binds to preferred port when available and writes actual port to discovery file', async () => {
      const preferredDir = join(tmpdir(), `genoffice-pref-${Date.now()}`)
      const prefServer = new AutomationServer({
        port: 48123,
        discoveryDir: preferredDir,
      })
      try {
        const boundPort = await prefServer.start()
        expect(boundPort).toBe(48123)
        expect(prefServer.getPort()).toBe(48123)

        const raw = readFileSync(prefServer.getDiscoveryFilePath(), 'utf8')
        const data = JSON.parse(raw)
        expect(data.port).toBe(48123)
        expect(data.host).toBe('127.0.0.1')
      } finally {
        await prefServer.stop()
        if (existsSync(preferredDir)) rmSync(preferredDir, { recursive: true, force: true })
      }
    })

    it('falls back to available localhost port when preferred port is occupied and records actual port', async () => {
      // 1. Occupy a test port with a dummy server
      const dummyServer = createServer((_req, res) => res.end('occupied'))
      await new Promise<void>((resolve) => dummyServer.listen(0, '127.0.0.1', () => resolve()))
      const occupiedPort = (dummyServer.address() as any).port

      const fallbackDir = join(tmpdir(), `genoffice-fall-${Date.now()}`)
      const fallbackServer = new AutomationServer({
        port: occupiedPort, // this preferred port is occupied!
        discoveryDir: fallbackDir,
      })

      try {
        // 2. Start automation server pointing to the occupied port
        const fallbackPort = await fallbackServer.start()

        // 3. Confirm fallback port is an allocated ephemeral port, different from occupiedPort
        expect(fallbackPort).toBeGreaterThan(0)
        expect(fallbackPort).not.toBe(occupiedPort)
        expect(fallbackServer.getHost()).toBe('127.0.0.1')

        // 4. Confirm discovery file records the ACTUAL fallback port
        const raw = readFileSync(fallbackServer.getDiscoveryFilePath(), 'utf8')
        const data = JSON.parse(raw)
        expect(data.port).toBe(fallbackPort)
        expect(data.host).toBe('127.0.0.1')
        expect(data.token).toBe(fallbackServer.getToken())

        // 5. Confirm server handles real requests on the fallback port
        const healthRes = await new Promise<{ status: number; data: any }>((resolve) => {
          httpRequest(
            {
              hostname: '127.0.0.1',
              port: fallbackPort,
              path: '/api/v1/health',
              method: 'GET',
              headers: { Host: `127.0.0.1:${fallbackPort}` },
            },
            (res) => {
              let body = ''
              res.on('data', (c) => (body += c))
              res.on('end', () => resolve({ status: res.statusCode || 0, data: JSON.parse(body) }))
            },
          ).end()
        })
        expect(healthRes.status).toBe(200)
        expect(healthRes.data.ok).toBe(true)
      } finally {
        await fallbackServer.stop()
        await new Promise<void>((resolve) => dummyServer.close(() => resolve()))
        if (existsSync(fallbackDir)) rmSync(fallbackDir, { recursive: true, force: true })
      }
    })
  })

  describe('Health Check Endpoint & Secret Isolation', () => {
    it('GET /api/v1/health returns ready status and NEVER leaks the auth token', async () => {
      const res = await request('GET', '/api/v1/health')
      expect(res.status).toBe(200)
      expect(res.data.ok).toBe(true)
      expect(res.data.status).toBe('ready')
      expect(res.data.protocol_version).toBe('1.0.0')
      expect(Array.isArray(res.data.capabilities)).toBe(true)
      expect(res.data.capabilities).toContain('document')
      expect(res.data.capabilities).toContain('presentation')
      expect(res.data.capabilities).toContain('spreadsheet')

      // CRITICAL: Token MUST NOT be present in health response
      expect(res.data).not.toHaveProperty('token')
      expect(JSON.stringify(res.data)).not.toContain(token)
    })
  })

  describe('Defense-in-Depth Security (Must-Fix #3)', () => {
    it('rejects invalid Host header with 403 Forbidden (DNS rebinding protection)', async () => {
      const res = await request('GET', '/api/v1/health', {
        Host: 'evil-attacker.com',
      })
      expect(res.status).toBe(403)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('FORBIDDEN_HOST')
    })

    it('rejects requests missing authentication token with 401 Unauthorized', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        { 'Content-Type': 'application/json' },
        JSON.stringify({ format: 'document', prompt: 'test' }),
      )
      expect(res.status).toBe(401)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('UNAUTHORIZED')
    })

    it('rejects requests with invalid authentication token with 401 Unauthorized', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': 'wrong-invalid-token',
        },
        JSON.stringify({ format: 'document', prompt: 'test' }),
      )
      expect(res.status).toBe(401)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('UNAUTHORIZED')
    })

    it('accepts requests with valid Bearer authorization header', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        JSON.stringify({ format: 'presentation', prompt: 'Generate slides' }),
      )
      expect(res.status).toBe(202)
      expect(res.data.ok).toBe(true)
      expect(res.data.status).toBe('queued')
    })
  })

  describe('Runtime Request Validation & Size Limits (Must-Fix #1)', () => {
    it('rejects payload exceeding 1MB size limit with 413 Payload Too Large', async () => {
      // Create a 1.2 MB buffer
      const largeData = 'a'.repeat(1.2 * 1024 * 1024)
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ format: 'document', prompt: largeData }),
      )
      expect(res.status).toBe(413)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('PAYLOAD_TOO_LARGE')
    })

    it('rejects empty body with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        '',
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
    })

    it('rejects unknown top-level fields with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Valid prompt',
          unexpected_malicious_prop: 'injected',
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('VALIDATION_ERROR')
      expect(res.data.error.field).toBe('unexpected_malicious_prop')
    })

    it('rejects unsupported format with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'invalid_format_xyz',
          prompt: 'Valid prompt',
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('format')
    })

    it('rejects empty or whitespace-only prompt with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: '    ',
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('prompt')
    })

    it('rejects invalid job_id pattern with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Valid prompt',
          job_id: 'bad job id with spaces!',
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('job_id')
    })

    it('rejects unknown fields in options with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'presentation',
          prompt: 'Valid prompt',
          options: {
            title: 'Valid Title',
            unknown_opt: 123,
          },
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('options.unknown_opt')
    })

    it('accepts completely valid payload with full metadata and options', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          job_id: 'job_custom_001',
          request_id: 'req_001',
          format: 'spreadsheet',
          prompt: 'Generate quarterly financial model',
          project_id: 'proj_123',
          session_id: 'sess_123',
          canonical_id: 'can_123',
          canonical_hash: 'a'.repeat(64),
          options: {
            title: 'Q3 Financials',
            approx_pages: 5,
            theme: 'corporate',
            audience: 'Executive',
            tone: 'formal',
            detail_level: 'high',
            save_directory: 'C:\\Users\\Admin\\Downloads\\LIMO\\workspace',
            sections_outline: ['P&L', 'Balance Sheet', 'Cash Flow'],
            custom_metadata: { department: 'Finance' },
          },
        }),
      )
      expect(res.status).toBe(202)
      expect(res.data.ok).toBe(true)
      expect(res.data.job_id).toBe('job_custom_001')
      expect(res.data.status).toBe('queued')
      expect(res.data.poll_url).toBe('/api/v1/jobs/job_custom_001')

      // Verify job record stored in manager
      const job = automationJobManager.getJob('job_custom_001')
      expect(job).toBeDefined()
      expect(job?.format).toBe('spreadsheet')
      expect(job?.options?.title).toBe('Q3 Financials')
      expect(job?.options?.approx_pages).toBe(5)
    })
  })

  describe('File & Attachment References (Item 1)', () => {
    it('accepts valid attachment references and persists them in the job record', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'presentation',
          prompt: 'Create slide deck using provided brand guidelines and architecture diagram',
          attachments: [
            {
              type: 'image',
              storage_ref: 'sources/architecture_v2.png',
              filename: 'architecture_v2.png',
              mime_type: 'image/png',
              size_bytes: 524288,
              metadata: { role: 'diagram' },
            },
            {
              type: 'document',
              storage_ref: 'sources/brand_guidelines.pdf',
              filename: 'brand_guidelines.pdf',
              mime_type: 'application/pdf',
            },
          ],
        }),
      )

      expect(res.status).toBe(202)
      expect(res.data.ok).toBe(true)
      const jobId = res.data.job_id

      // 1. Verify in manager
      const job = automationJobManager.getJob(jobId)
      expect(job).toBeDefined()
      expect(job?.attachments).toHaveLength(2)
      expect(job?.attachments?.[0].type).toBe('image')
      expect(job?.attachments?.[0].filename).toBe('architecture_v2.png')
      expect(job?.attachments?.[1].type).toBe('document')

      // 2. Verify in GET /api/v1/jobs/:job_id
      const getRes = await request('GET', `/api/v1/jobs/${jobId}`, {
        'X-GenOffice-Token': token,
      })
      expect(getRes.status).toBe(200)
      expect(getRes.data.attachments).toHaveLength(2)
      expect(getRes.data.attachments[0].storage_ref).toBe('sources/architecture_v2.png')
    })

    it('rejects attachment with path traversal in storage_ref with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Test prompt',
          attachments: [
            {
              type: 'document',
              storage_ref: '../../../../etc/passwd',
              filename: 'passwd.txt',
            },
          ],
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('attachments[0].storage_ref')
      expect(res.data.error.message).toContain('unsafe path traversal')
    })

    it('rejects attachment with directory separators in filename with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Test prompt',
          attachments: [
            {
              type: 'image',
              storage_ref: 'sources/valid.png',
              filename: 'subfolder/valid.png',
            },
          ],
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('attachments[0].filename')
      expect(res.data.error.message).toContain('directory separators')
    })

    it('rejects attachment with invalid type with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Test prompt',
          attachments: [
            {
              type: 'unsupported_type_xyz',
              storage_ref: 'sources/file.dat',
              filename: 'file.dat',
            },
          ],
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('attachments[0].type')
    })

    it('rejects attachment with unrecognized properties with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Test prompt',
          attachments: [
            {
              type: 'image',
              storage_ref: 'sources/file.png',
              filename: 'file.png',
              unknown_malicious_field: 'exploit',
            },
          ],
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('attachments[0].unknown_malicious_field')
    })

    it('rejects non-array attachments with 400 Bad Request', async () => {
      const res = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({
          format: 'document',
          prompt: 'Test prompt',
          attachments: 'not-an-array',
        }),
      )
      expect(res.status).toBe(400)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.field).toBe('attachments')
    })
  })

  describe('Cancel Semantics (Must-Fix #4)', () => {
    it('cancelling a QUEUED job immediately dequeues and sets status to cancelled with 200 OK', async () => {
      // 1. Submit job
      const submitRes = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ format: 'document', prompt: 'Queued job to cancel' }),
      )
      const jobId = submitRes.data.job_id

      expect(automationJobManager.getQueueLength()).toBe(1)

      // 2. Cancel
      const cancelRes = await request(
        'POST',
        `/api/v1/jobs/${jobId}/cancel`,
        { 'X-GenOffice-Token': token },
      )
      expect(cancelRes.status).toBe(200)
      expect(cancelRes.data.ok).toBe(true)
      expect(cancelRes.data.status).toBe('cancelled')
      expect(cancelRes.data.message).toContain('Queued job cancelled before execution')

      // 3. Verify queue is now empty and job status is cancelled
      expect(automationJobManager.getQueueLength()).toBe(0)
      const job = automationJobManager.getJob(jobId)
      expect(job?.status).toBe('cancelled')
      expect(job?.completed_at).toBeDefined()
    })

    it('cancelling a GENERATING job flags cancellation_requested: true and returns 202 Accepted', async () => {
      // Register a mock long-running runner that simulates D7.2 active loop
      let runnerStarted = false
      automationJobManager.setRunner(async (job) => {
        runnerStarted = true
        return new Promise<AutomationArtifact>((resolve) => {
          // Keep it running until checked
          setTimeout(() => {
            resolve({
              title: 'Done',
              file_format: '.docx',
              file_path: '/fake/path.docx',
            })
          }, 1000)
        })
      })

      // 1. Submit job -> runner immediately picks it up
      const submitRes = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ format: 'document', prompt: 'Long running task' }),
      )
      const jobId = submitRes.data.job_id

      expect(runnerStarted).toBe(true)
      const activeJob = automationJobManager.getJob(jobId)
      expect(activeJob?.status).toBe('generating')

      // 2. Cancel while generating
      const cancelRes = await request(
        'POST',
        `/api/v1/jobs/${jobId}/cancel`,
        { 'X-GenOffice-Token': token },
      )
      expect(cancelRes.status).toBe(202)
      expect(cancelRes.data.ok).toBe(true)
      expect(cancelRes.data.status).toBe('generating')
      expect(cancelRes.data.cancellation_requested).toBe(true)
      expect(cancelRes.data.message).toContain('Cancellation signal registered; awaiting runner termination')

      // Verify flag on record
      expect(activeJob?.cancellation_requested).toBe(true)
    })

    it('cancelling a non-existent job returns 404 Not Found', async () => {
      const res = await request(
        'POST',
        '/api/v1/jobs/job_nonexistent_xyz/cancel',
        { 'X-GenOffice-Token': token },
      )
      expect(res.status).toBe(404)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('JOB_NOT_FOUND')
    })

    it('cancelling an already cancelled job returns 409 Conflict', async () => {
      const submitRes = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ format: 'document', prompt: 'Job to double cancel' }),
      )
      const jobId = submitRes.data.job_id

      // First cancel
      await request('POST', `/api/v1/jobs/${jobId}/cancel`, { 'X-GenOffice-Token': token })

      // Second cancel
      const secondRes = await request(
        'POST',
        `/api/v1/jobs/${jobId}/cancel`,
        { 'X-GenOffice-Token': token },
      )
      expect(secondRes.status).toBe(409)
      expect(secondRes.data.ok).toBe(false)
      expect(secondRes.data.error.code).toBe('ILLEGAL_STATE_TRANSITION')
    })
  })

  describe('Job Status Polling Endpoint', () => {
    it('GET /api/v1/jobs/:job_id returns current queued status', async () => {
      const submitRes = await request(
        'POST',
        '/api/v1/generate',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ format: 'presentation', prompt: 'Test slides' }),
      )
      const jobId = submitRes.data.job_id

      const getRes = await request('GET', `/api/v1/jobs/${jobId}`, {
        'X-GenOffice-Token': token,
      })
      expect(getRes.status).toBe(200)
      expect(getRes.data.ok).toBe(true)
      expect(getRes.data.job_id).toBe(jobId)
      expect(getRes.data.status).toBe('queued')
      expect(getRes.data.format).toBe('presentation')
      expect(getRes.data.cancellation_requested).toBe(false)
    })

    it('GET /api/v1/jobs/:job_id returns 404 for unknown job', async () => {
      const res = await request('GET', '/api/v1/jobs/unknown_job_999', {
        'X-GenOffice-Token': token,
      })
      expect(res.status).toBe(404)
      expect(res.data.ok).toBe(false)
      expect(res.data.error.code).toBe('JOB_NOT_FOUND')
    })
  })

  describe('Format Specific Aliases', () => {
    it('POST /api/v1/genoffice/docs assigns default document format', async () => {
      const res = await request(
        'POST',
        '/api/v1/genoffice/docs',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ prompt: 'Write an executive memo' }),
      )
      expect(res.status).toBe(202)
      expect(res.data.format).toBe('document')
    })

    it('POST /api/v1/genoffice/slides assigns default presentation format', async () => {
      const res = await request(
        'POST',
        '/api/v1/genoffice/slides',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ prompt: 'Create 10 slides on AI' }),
      )
      expect(res.status).toBe(202)
      expect(res.data.format).toBe('presentation')
    })

    it('POST /api/v1/genoffice/sheets assigns default spreadsheet format', async () => {
      const res = await request(
        'POST',
        '/api/v1/genoffice/sheets',
        {
          'Content-Type': 'application/json',
          'X-GenOffice-Token': token,
        },
        JSON.stringify({ prompt: 'Build a financial projection table' }),
      )
      expect(res.status).toBe(202)
      expect(res.data.format).toBe('spreadsheet')
    })
  })
})
