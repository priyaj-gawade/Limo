import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { request as httpRequest } from 'node:http'
import { homedir } from 'node:os'
import { join } from 'node:path'
import JSZip from 'jszip'

/**
 * Authoritative Live Probe for Phase D7.5: Artifact Handoff, Native Document, Real Thumbnail, Limo Ingestion & Open
 *
 * Verifies End-to-End:
 * 1. GenOffice Electron process boots with automation enabled.
 * 2. Discovery file ~/.genoffice/automation.json is created.
 * 3. Health check GET /api/v1/health returns ready.
 * 4. Job generation: POST /api/v1/generate with format='document'.
 * 5. Full lifecycle poll: queued -> generating -> completed.
 * 6. Native .docx document verified on disk (size, SHA-256, OpenXML [Content_Types].xml & document.xml).
 * 7. Real thumbnail (.thumb.png) captured via wc.capturePage(), verified on disk (PNG magic bytes, size > 0).
 * 8. Limo ingestion via python verify_d7_5_live.py:
 *    - Handoff into Limo sandboxed storage
 *    - Thumbnail endpoint: GET /api/v1/artifacts/{id}/thumbnail (200 image/png)
 *    - Download endpoint: GET /api/v1/artifacts/{id}/download (200 attachment)
 *    - Workspace open endpoint: POST /api/v1/artifacts/{id}/open (calls GenOffice POST /api/v1/open loopback)
 *    - Chat hydration: GET /api/v1/chats/{session_id}/messages (resolves artifact & execution summary)
 */

const DISCOVERY_PATH = join(homedir(), '.genoffice', 'automation.json')

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function doRequest(options, postData) {
  return new Promise((resolve, reject) => {
    const req = httpRequest(options, (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8')
        let data = raw
        try {
          data = JSON.parse(raw)
        } catch {
          // fallback
        }
        resolve({
          statusCode: res.statusCode || 0,
          headers: res.headers,
          data,
        })
      })
    })

    req.on('error', reject)
    if (postData) {
      req.write(postData)
    }
    req.end()
  })
}

async function runCommand(command, args, cwd) {
  return new Promise((resolve, reject) => {
    console.log(`[Exec] ${command} ${args.join(' ')} (in ${cwd})`)
    const proc = spawn(command, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
      },
    })

    let stdout = ''
    let stderr = ''

    proc.stdout.on('data', (d) => {
      const text = d.toString()
      stdout += text
      process.stdout.write(text)
    })

    proc.stderr.on('data', (d) => {
      const text = d.toString()
      stderr += text
      process.stderr.write(text)
    })

    proc.on('close', (code) => {
      if (code === 0) {
        resolve({ code, stdout, stderr })
      } else {
        reject(new Error(`Command failed with code ${code}: ${stderr}`))
      }
    })
  })
}

async function main() {
  console.log('###############################################################')
  console.log('  GENOFFICE PHASE D7.5 AUTHORITATIVE END-TO-END LIVE PROBE     ')
  console.log('  Full Loop: GenOffice -> Native Doc + Thumbnail -> Limo Ingestion ')
  console.log('###############################################################\n')

  let metadata = null
  let spawnedChild = null

  // Check if GenOffice is already running
  if (existsSync(DISCOVERY_PATH)) {
    try {
      const existing = JSON.parse(readFileSync(DISCOVERY_PATH, 'utf8'))
      if (existing && existing.host && existing.port && existing.token) {
        const h = await doRequest({
          hostname: existing.host,
          port: existing.port,
          path: '/api/v1/health',
          method: 'GET',
        })
        if (h.statusCode === 200 && h.data?.status === 'ready') {
          console.log(`[Setup] Attached to existing healthy GenOffice instance at ${existing.host}:${existing.port}`)
          metadata = existing
        }
      }
    } catch {
      // not running
    }
  }

  if (!metadata) {
    if (existsSync(DISCOVERY_PATH)) {
      try {
        rmSync(DISCOVERY_PATH, { force: true })
      } catch {}
    }

    const electronBin =
      process.platform === 'win32'
        ? join(process.cwd(), 'node_modules', 'electron', 'dist', 'electron.exe')
        : join(process.cwd(), 'node_modules', '.bin', 'electron')

    console.log(`[Setup] Spawning GenOffice via: ${electronBin} apps/shell`)
    spawnedChild = spawn(electronBin, ['apps/shell'], {
      cwd: process.cwd(),
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        GENOFFICE_AUTOMATION_ENABLED: 'true',
      },
    })

    spawnedChild.stderr.on('data', (d) => {
      const msg = d.toString().trim()
      if (msg && !msg.includes('GL') && !msg.includes('GPU')) console.log(`[GenOffice Stderr] ${msg}`)
    })

    spawnedChild.stdout.on('data', (d) => {
      const msg = d.toString().trim()
      if (msg) console.log(`[GenOffice Stdout] ${msg}`)
    })

    console.log('[Setup] Waiting for ~/.genoffice/automation.json...')
    const deadline = Date.now() + 40000

    while (Date.now() < deadline) {
      if (existsSync(DISCOVERY_PATH)) {
        try {
          const content = readFileSync(DISCOVERY_PATH, 'utf8')
          const parsed = JSON.parse(content)
          if (parsed && parsed.host && parsed.port && parsed.token) {
            metadata = parsed
            break
          }
        } catch {}
      }
      await sleep(300)
    }

    if (!metadata) {
      throw new Error('Timed out waiting for GenOffice discovery metadata file.')
    }
  }

  console.log('✓ GenOffice Discovery metadata active:')
  console.log(`  Host:             ${metadata.host}`)
  console.log(`  Port:             ${metadata.port}`)
  console.log(`  Session ID:       ${metadata.session_id}`)
  console.log(`  PID:              ${metadata.pid}\n`)

  const authHeader = `Bearer ${metadata.token}`

  // Health check
  console.log('[Setup] Checking GET /api/v1/health...')
  const healthRes = await doRequest({
    hostname: metadata.host,
    port: metadata.port,
    path: '/api/v1/health',
    method: 'GET',
  })

  if (healthRes.statusCode !== 200 || healthRes.data?.status !== 'ready') {
    throw new Error(`Health check failed: ${healthRes.statusCode} - ${JSON.stringify(healthRes.data)}`)
  }
  console.log('✓ Automation server is ready (HTTP 200)\n')

  try {
    // 1. Generate real native document
    const title = `D75_Live_Doc_${Date.now()}`
    console.log(`[Generation] Submitting real document job: "${title}"...`)
    const genPayload = JSON.stringify({
      format: 'document',
      prompt: 'Produce an executive overview of quarterly resilience with clear section headers.',
      options: { title },
    })

    const genRes = await doRequest(
      {
        hostname: metadata.host,
        port: metadata.port,
        path: '/api/v1/generate',
        method: 'POST',
        headers: {
          Authorization: authHeader,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(genPayload),
        },
      },
      genPayload,
    )

    if (genRes.statusCode !== 200 && genRes.statusCode !== 202) {
      throw new Error(`Failed to enqueue document job: HTTP ${genRes.statusCode} - ${JSON.stringify(genRes.data)}`)
    }

    const jobId = genRes.data.job_id
    console.log(`✓ Job enqueued: id=${jobId}`)

    // 2. Poll through full lifecycle
    console.log(`  Polling GET /api/v1/jobs/${jobId} through full D7.5 lifecycle...`)
    let finalJob = null
    let lastSubstate = ''
    const jobDeadline = Date.now() + 180000 // 3 minutes

    while (Date.now() < jobDeadline) {
      const pollRes = await doRequest({
        hostname: metadata.host,
        port: metadata.port,
        path: `/api/v1/jobs/${jobId}`,
        method: 'GET',
        headers: { Authorization: authHeader },
      })

      const job = pollRes.data?.job || pollRes.data
      if (pollRes.statusCode === 200 && job && job.status) {
        const substate = job.progress?.substate || '(none)'
        const message = job.progress?.message || ''

        if (substate !== lastSubstate) {
          console.log(`  -> Macro: [${job.status}] | Substate: [${substate}] | ${message}`)
          lastSubstate = substate
        }

        if (job.status === 'completed' || job.status === 'failed') {
          finalJob = job
          break
        }
      }
      await sleep(600)
    }

    if (!finalJob || finalJob.status !== 'completed') {
      throw new Error(`Job failed or timed out: ${JSON.stringify(finalJob)}`)
    }

    const artifact = finalJob.artifact
    if (!artifact) {
      throw new Error('Completed job is missing artifact object.')
    }

    console.log('\n[GenOffice Native Artifact Verification]:')
    console.log(`- Title:           ${artifact.title}`)
    console.log(`- Format:          ${artifact.file_format}`)
    console.log(`- Path:            ${artifact.file_path}`)
    console.log(`- Size:            ${artifact.size_bytes} bytes`)
    console.log(`- Content Hash:    ${artifact.content_hash}`)
    console.log(`- Thumbnail Path:  ${artifact.thumbnail_path}`)

    // Verify document on disk
    if (!existsSync(artifact.file_path)) {
      throw new Error(`Document missing on disk at ${artifact.file_path}`)
    }
    const docBytes = readFileSync(artifact.file_path)
    if (docBytes.length !== artifact.size_bytes) {
      throw new Error(`Document size mismatch: disk=${docBytes.length}, artifact=${artifact.size_bytes}`)
    }
    const computedDocHash = createHash('sha256').update(docBytes).digest('hex')
    if (computedDocHash !== artifact.content_hash) {
      throw new Error(`Document SHA-256 mismatch`)
    }
    console.log('✓ Physical document verified on disk and checksum matched')

    // Verify OpenXML structure
    const zip = await JSZip.loadAsync(docBytes)
    if (!zip.file('[Content_Types].xml')) throw new Error('Missing [Content_Types].xml in DOCX')
    if (!zip.file('word/document.xml')) throw new Error('Missing word/document.xml in DOCX')
    console.log('✓ Document OpenXML structural integrity verified')

    // Verify thumbnail on disk
    if (!artifact.thumbnail_path || !existsSync(artifact.thumbnail_path)) {
      throw new Error(`Thumbnail missing on disk at ${artifact.thumbnail_path}`)
    }
    const thumbBytes = readFileSync(artifact.thumbnail_path)
    if (thumbBytes.length === 0) {
      throw new Error('Thumbnail file is empty (0 bytes)')
    }
    // Verify PNG magic header: 89 50 4E 47 0D 0A 1A 0A
    const pngHeader = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    if (!thumbBytes.subarray(0, 8).equals(pngHeader)) {
      throw new Error('Thumbnail does not have valid PNG header magic bytes')
    }
    console.log(`✓ Real thumbnail captured: ${thumbBytes.length} bytes, valid PNG header`)

    // 3. Execute Limo Ingestion & REST Endpoints verification
    console.log('\n===============================================================')
    console.log('  EXECUTING LIMO BACKEND D7.5 VERIFICATION (Ingest, Endpoints, Hydration, Open)')
    console.log('===============================================================')

    const limoBackendDir = join(process.cwd(), '..', '..', 'backend')
    await runCommand(
      'python',
      [
        'verify_d7_5_live.py',
        '--file-path',
        `"${artifact.file_path}"`,
        '--thumb-path',
        `"${artifact.thumbnail_path}"`,
        '--title',
        `"${artifact.title}"`,
      ],
      limoBackendDir,
    )

    console.log('\n###############################################################')
    console.log('  PHASE D7.5 AUTHORITATIVE END-TO-END PROBE: 100% SUCCESSFUL!  ')
    console.log('  - GenOffice Document Generation:   PASS                     ')
    console.log('  - Native File & OpenXML Integrity: PASS                     ')
    console.log('  - Real Thumbnail Capture:          PASS                     ')
    console.log('  - Limo Sandboxed Ingestion:        PASS                     ')
    console.log('  - GET /thumbnail Endpoint:         PASS                     ')
    console.log('  - GET /download Endpoint:          PASS                     ')
    console.log('  - POST /open Workspace Loopback:   PASS                     ')
    console.log('  - Chat History Hydration:          PASS                     ')
    console.log('###############################################################\n')
  } finally {
    if (spawnedChild && !spawnedChild.killed) {
      console.log('[Teardown] Terminating spawned GenOffice process...')
      if (process.platform === 'win32' && spawnedChild.pid) {
        try {
          spawn('taskkill', ['/F', '/T', '/PID', String(spawnedChild.pid)])
        } catch {}
      }
      spawnedChild.kill('SIGTERM')
      await sleep(1500)
    }
  }
}

main().catch((err) => {
  console.error('\n❌ LIVE PROBE D7.5 FAILED:', err)
  process.exit(1)
})
