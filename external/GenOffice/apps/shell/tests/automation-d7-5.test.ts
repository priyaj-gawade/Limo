import { writeFileSync, unlinkSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { request as httpRequest } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AutomationServer } from '../src/main/automation-server'
import type { AutomationArtifact } from '../src/main/automation-types'

describe('GenOffice Local Automation Interface (D7.5 — Open & Thumbnail)', () => {
  let server: AutomationServer
  let port: number
  let testDir: string
  let token: string
  let tempFilePath: string

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
    testDir = join(tmpdir(), `genoffice-d7-5-test-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`)
    mkdirSync(testDir, { recursive: true })
    token = 'd7_5_secret_token_1234567890abcdef'
    tempFilePath = join(testDir, 'test_doc.docx')
    writeFileSync(tempFilePath, Buffer.from('PK\x03\x04test-openxml-content'))

    server = new AutomationServer({
      port: 0,
      host: '127.0.0.1',
      token,
      discoveryDir: testDir,
    })
    port = await server.start()
  })

  afterEach(async () => {
    await server.stop()
    if (existsSync(testDir)) {
      rmSync(testDir, { recursive: true, force: true })
    }
  })

  it('rejects POST /api/v1/open without authorization header', async () => {
    const res = await request('POST', '/api/v1/open', {}, JSON.stringify({ file_path: tempFilePath }))
    expect(res.status).toBe(401)
    expect(res.data.ok).toBe(false)
    expect(res.data.error.code).toBe('UNAUTHORIZED')
  })

  it('rejects POST /api/v1/open with empty file_path', async () => {
    const res = await request(
      'POST',
      '/api/v1/open',
      { 'x-genoffice-token': token, 'Content-Type': 'application/json' },
      JSON.stringify({ file_path: '' }),
    )
    expect(res.status).toBe(400)
    expect(res.data.ok).toBe(false)
    expect(res.data.error.code).toBe('INVALID_REQUEST')
  })

  it('returns 404 for non-existent file path', async () => {
    const missingPath = join(testDir, 'missing_file.docx')
    const res = await request(
      'POST',
      '/api/v1/open',
      { 'x-genoffice-token': token, 'Content-Type': 'application/json' },
      JSON.stringify({ file_path: missingPath }),
    )
    expect(res.status).toBe(404)
    expect(res.data.ok).toBe(false)
    expect(res.data.error.code).toBe('FILE_NOT_FOUND')
  })

  it('successfully triggers documentOpener callback on valid file path', async () => {
    let openedPath = ''
    server.setDocumentOpener((filePath: string) => {
      openedPath = filePath
      return true
    })

    const res = await request(
      'POST',
      '/api/v1/open',
      { 'x-genoffice-token': token, 'Content-Type': 'application/json' },
      JSON.stringify({ file_path: tempFilePath }),
    )
    expect(res.status).toBe(200)
    expect(res.data.ok).toBe(true)
    expect(res.data.opened).toBe(true)
    expect(res.data.file_path).toBe(tempFilePath)
    expect(openedPath).toBe(tempFilePath)
  })

  it('verifies AutomationArtifact interface accepts thumbnail_path', () => {
    const art: AutomationArtifact = {
      title: 'Quarterly Analysis',
      file_format: 'document',
      file_path: tempFilePath,
      thumbnail_path: `${tempFilePath}.thumb.png`,
      size_bytes: 1234,
      content_hash: '9b36bb1286c04f9e31d4d8efbc75a1334887968dbbc034d3b64f33666b6e41b3',
    }
    expect(art.thumbnail_path).toBe(`${tempFilePath}.thumb.png`)
  })
})
