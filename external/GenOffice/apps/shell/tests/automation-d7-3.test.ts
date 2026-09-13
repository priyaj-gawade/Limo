import { existsSync, mkdirSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import JSZip from 'jszip'
import { PDFDocument } from 'pdf-lib'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { AutomationJobManager } from '../src/main/automation-manager'
import { AutomationExecutionRunner } from '../src/main/automation-runner'
import type { AutomationJobRecord } from '../src/main/automation-types'
import { AutomationViewManager } from '../src/main/automation-view-manager'

interface FakeWebContents {
  id: number
  send: ReturnType<typeof vi.fn>
  once: ReturnType<typeof vi.fn>
  on: ReturnType<typeof vi.fn>
  removeListener: ReturnType<typeof vi.fn>
  isDestroyed: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  setBackgroundThrottling: ReturnType<typeof vi.fn>
  setAudioMuted: ReturnType<typeof vi.fn>
  emit: (event: string, ...args: any[]) => void
  listeners: Map<string, ((...args: any[]) => void)[]>
}

interface FakeView {
  webContents: FakeWebContents
  setVisible: ReturnType<typeof vi.fn>
  setBounds: ReturnType<typeof vi.fn>
}

const { ipcMainHandlers, activeViews, createDocsView, createSlidesView, createSheetsView, createPdfView } = vi.hoisted(() => {
  let nextId = 200
  const activeViews: FakeView[] = []

  const makeView = () => {
    const listeners = new Map<string, ((...args: any[]) => void)[]>()
    const fakeWc: FakeWebContents = {
      id: nextId++,
      listeners,
      send: vi.fn(),
      once: vi.fn((event: string, handler: (...args: any[]) => void) => {
        const wrapper = (...args: any[]) => {
          const list = listeners.get(event) || []
          const idx = list.indexOf(wrapper)
          if (idx !== -1) list.splice(idx, 1)
          handler(...args)
        }
        const list = listeners.get(event) || []
        list.push(wrapper)
        listeners.set(event, list)
      }),
      on: vi.fn((event: string, handler: (...args: any[]) => void) => {
        const list = listeners.get(event) || []
        list.push(handler)
        listeners.set(event, list)
      }),
      removeListener: vi.fn((event: string, handler: (...args: any[]) => void) => {
        const list = listeners.get(event) || []
        const idx = list.indexOf(handler)
        if (idx !== -1) list.splice(idx, 1)
      }),
      emit: (event: string, ...args: any[]) => {
        const list = listeners.get(event) || []
        for (const fn of [...list]) {
          fn(...args)
        }
      },
      isDestroyed: vi.fn(() => false),
      close: vi.fn(),
      setBackgroundThrottling: vi.fn(),
      setAudioMuted: vi.fn(),
    }
    const view: FakeView = {
      webContents: fakeWc,
      setVisible: vi.fn(),
      setBounds: vi.fn(),
    }
    activeViews.push(view)
    return view
  }

  return {
    ipcMainHandlers: new Map<string, (event: any, payload: any) => void>(),
    activeViews,
    createDocsView: vi.fn(() => makeView()),
    createSlidesView: vi.fn(() => makeView()),
    createSheetsView: vi.fn(() => makeView()),
    createPdfView: vi.fn(() => makeView()),
  }
})

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => tmpdir()),
  },
  BrowserWindow: class {},
  ipcMain: {
    on: vi.fn((channel: string, handler: (event: any, payload: any) => void) => {
      ipcMainHandlers.set(channel, handler)
    }),
    removeListener: vi.fn(),
  },
}))

const testSaveDir = join(tmpdir(), `genoffice-d73-test-${Date.now()}`)

vi.mock('../../docs/src/main/docs-main', () => ({
  createDocsView: (...args: unknown[]) => createDocsView(...(args as [])),
  markDocsNewBlank: vi.fn(),
  defaultSaveDir: () => testSaveDir,
  uniquePathIn: (dir: string, name: string) => join(dir, name),
}))

vi.mock('../../slides/src/main/slides-main', () => ({
  createSlidesView: (...args: unknown[]) => createSlidesView(...(args as [])),
  defaultSaveDir: () => testSaveDir,
  uniquePathIn: (dir: string, name: string) => join(dir, name),
}))

vi.mock('../../sheets/src/main/sheets-main', () => ({
  createSheetsView: (...args: unknown[]) => createSheetsView(...(args as [])),
  setSheetsNewBlank: vi.fn(),
  queueWorkbookForView: vi.fn(),
}))

vi.mock('../../sheets/src/gateway/csv-import', () => ({
  blankXlsxBuffer: vi.fn(async () => {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('xl/workbook.xml', '<workbook/>')
    zip.file('xl/worksheets/sheet1.xml', '<worksheet/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }),
}))

vi.mock('../../pdf/src/main/pdf-main', () => ({
  createPdfView: (...args: unknown[]) => createPdfView(...(args as [])),
  markPdfUntitledPath: vi.fn(),
}))

vi.mock('../../pdf/src/main/blank-pdf', () => ({
  blankPdfBuffer: vi.fn(async () => {
    const doc = await PDFDocument.create()
    doc.addPage([600, 400])
    const bytes = await doc.save()
    return Buffer.from(bytes)
  }),
}))

describe('Background Execution & Lifecycle Hardening (D7.3)', () => {
  let fakeWindow: any
  let childViews: FakeView[]
  let viewManager: AutomationViewManager
  let jobManager: AutomationJobManager
  let runner: AutomationExecutionRunner

  beforeAll(() => {
    if (!existsSync(testSaveDir)) {
      mkdirSync(testSaveDir, { recursive: true })
    }
  })

  afterAll(() => {
    try {
      rmSync(testSaveDir, { recursive: true, force: true })
    } catch {
      /* ignore */
    }
  })

  async function createValidPptxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('ppt/presentation.xml', '<presentation/>')
    zip.file('ppt/slides/slide1.xml', '<slide/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

  async function createValidXlsxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('xl/workbook.xml', '<workbook/>')
    zip.file('xl/worksheets/sheet1.xml', '<worksheet/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

  beforeEach(() => {
    ipcMainHandlers.clear()
    activeViews.length = 0
    childViews = []
    vi.clearAllMocks()

    fakeWindow = {
      isDestroyed: vi.fn(() => false),
      contentView: {
        addChildView: vi.fn((view: FakeView) => {
          childViews.push(view)
        }),
        removeChildView: vi.fn((view: FakeView) => {
          const idx = childViews.indexOf(view)
          if (idx !== -1) childViews.splice(idx, 1)
        }),
      },
    }

    viewManager = new AutomationViewManager(fakeWindow)
    jobManager = new AutomationJobManager()
    runner = new AutomationExecutionRunner(viewManager, jobManager, fakeWindow)
  })

  describe('1. Background View Throttling, Audio & Navigation Protection', () => {
    it('disables background throttling and mutes audio when creating hidden view', async () => {
      const handle = await viewManager.createHiddenView('document')
      expect(handle.view.webContents.setBackgroundThrottling).toHaveBeenCalledWith(false)
      expect(handle.view.webContents.setAudioMuted).toHaveBeenCalledWith(true)
      expect(handle.view.setVisible).toHaveBeenCalledWith(false)
      expect(handle.view.setBounds).toHaveBeenCalledWith({ x: 0, y: 0, width: 1280, height: 800 })
    })

    it('attaches will-navigate security guard to block external navigation', async () => {
      const handle = await viewManager.createHiddenView('document')
      const wc = handle.view.webContents
      const navListeners = wc.listeners.get('will-navigate') || []
      expect(navListeners.length).toBeGreaterThan(0)

      const preventDefault = vi.fn()
      // Local app URL: allowed
      navListeners[0]({ preventDefault }, 'http://localhost:5173/editor')
      expect(preventDefault).not.toHaveBeenCalled()

      // External URL: blocked
      navListeners[0]({ preventDefault }, 'https://malicious-external-site.com')
      expect(preventDefault).toHaveBeenCalled()
    })
  })

  describe('2. Crash Detection and Recovery (render-process-gone)', () => {
    it('catches render-process-gone, fails job with RENDERER_PROCESS_GONE, and cleans view', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'document',
        prompt: 'Generate an analysis document',
      })

      // Wait for STARTING substate
      await vi.waitFor(() => {
        expect(jobManager.getJob(job.job_id)?.status).toBe('generating')
        expect(activeViews.length).toBe(1)
      })

      const currentView = activeViews[0]

      // Signal renderer ready
      const readyHandler = ipcMainHandlers.get('automation:renderer-ready')
      expect(readyHandler).toBeDefined()
      readyHandler!({ sender: { id: currentView.webContents.id } }, { format: 'document' })

      // Wait for RUNNING_AGENT
      await vi.waitFor(() => {
        expect(jobManager.getJob(job.job_id)?.progress?.substate).toBe('RUNNING_AGENT')
      })

      // Simulate renderer crash
      currentView.webContents.emit('render-process-gone', {}, { reason: 'crashed', exitCode: 139 })

      // Verify job failed with RENDERER_PROCESS_GONE
      await vi.waitFor(() => {
        const failedJob = jobManager.getJob(job.job_id)
        expect(failedJob?.status).toBe('failed')
        expect(failedJob?.error?.code).toBe('RENDERER_PROCESS_GONE')
        expect(failedJob?.error?.message).toContain('crashed')
      })

      // Verify view is destroyed and handle is freed
      expect(viewManager.getActiveHandle()).toBeNull()
      expect(childViews.length).toBe(0)
    })

    it('drains subsequent queued job cleanly after a previous job crash', async () => {
      jobManager.setRunner(runner.getRunner())

      const job1 = jobManager.enqueue({
        format: 'document',
        prompt: 'Job 1 will crash',
      })
      const job2 = jobManager.enqueue({
        format: 'presentation',
        prompt: 'Job 2 will succeed',
      })

      // Simulate ready for Job 1
      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })
      const view1 = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')!({ sender: { id: view1.webContents.id } }, { format: 'document' })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job1.job_id)?.progress?.substate).toBe('RUNNING_AGENT')
      })

      // Crash Job 1
      view1.webContents.emit('render-process-gone', {}, { reason: 'oom', exitCode: 137 })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job1.job_id)?.status).toBe('failed')
      })

      // Job 2 should now automatically start
      await vi.waitFor(() => {
        expect(jobManager.getJob(job2.job_id)?.status).toBe('generating')
        expect(activeViews.length).toBe(2)
      })

      const view2 = activeViews[1]
      ipcMainHandlers.get('automation:renderer-ready')!({ sender: { id: view2.webContents.id } }, { format: 'presentation' })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job2.job_id)?.progress?.substate).toBe('RUNNING_AGENT')
      })

      // Complete Job 2
      ipcMainHandlers.get('automation:agent-done')!({}, {
        job_id: job2.job_id,
        ok: true,
        turns: 2,
        tools_executed: ['createSlide'],
        content_detected: true,
      })

      const pptxBuf = await createValidPptxBuffer()
      const job2SavedPath = join(testSaveDir, 'Presentation.pptx')
      writeFileSync(job2SavedPath, pptxBuf)
      ipcMainHandlers.get('automation:file-saved')!({ sender: { id: view2.webContents.id } }, {
        job_id: job2.job_id,
        file_path: job2SavedPath,
        file_format: 'presentation',
        title: 'Presentation',
      })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job2.job_id)?.status).toBe('completed')
      })
    })
  })

  describe('3. Execution Timeout Escalation', () => {
    it('forced timeout-path verification using an intentionally minimal 100 ms threshold', async () => {
      jobManager.setRunner(runner.getRunner())

      const job = jobManager.enqueue({
        format: 'document',
        prompt: 'Job with ultra-short timeout',
        options: {
          timeout_ms: 100, // 100ms timeout
        },
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })
      const currentView = activeViews[0]

      // Signal ready
      ipcMainHandlers.get('automation:renderer-ready')!({ sender: { id: currentView.webContents.id } }, { format: 'document' })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job.job_id)?.progress?.substate).toBe('RUNNING_AGENT')
      })

      // Wait for timeout escalation to trigger cancellation and then force-abort
      await vi.waitFor(
        () => {
          const timedOutJob = jobManager.getJob(job.job_id)
          expect(timedOutJob?.status).toBe('failed')
          expect(timedOutJob?.error?.code).toBe('EXECUTION_TIMEOUT')
        },
        { timeout: 7000 },
      )

      expect(viewManager.getActiveHandle()).toBeNull()
    })
  })

  describe('4. Unresponsive Event Handling', () => {
    it('logs warning and updates progress without failing job when unresponsive event fires', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'spreadsheet',
        prompt: 'Large spreadsheet calculation',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })
      const currentView = activeViews[0]

      ipcMainHandlers.get('automation:renderer-ready')!({ sender: { id: currentView.webContents.id } }, { format: 'spreadsheet' })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job.job_id)?.progress?.substate).toBe('RUNNING_AGENT')
      })

      // Emit unresponsive
      currentView.webContents.emit('unresponsive')

      const updatedJob = jobManager.getJob(job.job_id)
      expect(updatedJob?.status).toBe('generating')
      expect(updatedJob?.progress?.message).toContain('unresponsive')

      // Complete normally afterwards
      ipcMainHandlers.get('automation:agent-done')!({}, {
        job_id: job.job_id,
        ok: true,
        turns: 1,
        tools_executed: ['setCell'],
        content_detected: true,
      })

      const xlsxBuf = await createValidXlsxBuffer()
      const jobSavedPath = join(testSaveDir, 'Spreadsheet.xlsx')
      writeFileSync(jobSavedPath, xlsxBuf)
      ipcMainHandlers.get('automation:file-saved')!({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        file_path: jobSavedPath,
        file_format: 'spreadsheet',
        title: 'Spreadsheet',
      })

      await vi.waitFor(() => {
        expect(jobManager.getJob(job.job_id)?.status).toBe('completed')
      })
    })
  })

  describe('5. Lifecycle Teardown Idempotency', () => {
    it('is completely safe and idempotent to call destroyActiveView multiple times', async () => {
      await viewManager.createHiddenView('document')
      expect(viewManager.getActiveHandle()).not.toBeNull()

      viewManager.destroyActiveView()
      expect(viewManager.getActiveHandle()).toBeNull()

      // Calling again should not throw
      expect(() => viewManager.destroyActiveView()).not.toThrow()
      expect(viewManager.getActiveHandle()).toBeNull()
    })
  })

  describe('6. Invariant: ONE job -> ONE terminal state -> ONE cleanup -> queue released exactly once', () => {
    it('guarantees that once a job fails (e.g. via timeout), late callbacks or complete calls cannot overwrite state', () => {
      const job = jobManager.enqueue({
        format: 'document',
        prompt: 'Test invariant',
      })

      // Manually advance to generating for direct manager invariant test
      const rec = jobManager.getJob(job.job_id)!
      rec.status = 'generating'
      ;(jobManager as any).activeJobId = job.job_id

      // 1. Fail the job (e.g. timeout)
      jobManager.failJob(job.job_id, {
        code: 'EXECUTION_TIMEOUT',
        message: 'Timeout fired',
      })

      const afterFail = jobManager.getJob(job.job_id)!
      expect(afterFail.status).toBe('failed')
      expect(afterFail.error?.code).toBe('EXECUTION_TIMEOUT')
      const completedAt = afterFail.completed_at
      expect(completedAt).toBeDefined()
      expect(jobManager.getActiveCount()).toBe(0)

      // 2. Late completion attempt (e.g. delayed agent-done callback)
      jobManager.completeJob(job.job_id, {
        title: 'Late Artifact',
        file_format: 'docx',
        file_path: '/tmp/late.docx',
      })

      // Assert state did NOT change to completed
      const afterLateComplete = jobManager.getJob(job.job_id)!
      expect(afterLateComplete.status).toBe('failed')
      expect(afterLateComplete.artifact).toBeNull()
      expect(afterLateComplete.completed_at).toBe(completedAt)

      // 3. Late cancellation confirmation attempt
      jobManager.finalizeCancellation(job.job_id)
      expect(jobManager.getJob(job.job_id)!.status).toBe('failed')

      // 4. Duplicate fail call
      jobManager.failJob(job.job_id, { code: 'OTHER_ERR', message: 'Duplicate fail' })
      expect(jobManager.getJob(job.job_id)!.error?.code).toBe('EXECUTION_TIMEOUT')
    })

    it('guarantees that once a job is cancelled, late complete or fail calls cannot overwrite state', () => {
      const job = jobManager.enqueue({
        format: 'presentation',
        prompt: 'Cancel test',
      })

      const rec = jobManager.getJob(job.job_id)!
      rec.status = 'generating'
      ;(jobManager as any).activeJobId = job.job_id

      jobManager.finalizeCancellation(job.job_id)
      const afterCancel = jobManager.getJob(job.job_id)!
      expect(afterCancel.status).toBe('cancelled')
      const completedAt = afterCancel.completed_at

      // Late complete
      jobManager.completeJob(job.job_id, {
        title: 'Should not exist',
        file_format: 'pptx',
        file_path: '/tmp/test.pptx',
      })
      expect(jobManager.getJob(job.job_id)!.status).toBe('cancelled')
      expect(jobManager.getJob(job.job_id)!.artifact).toBeNull()
      expect(jobManager.getJob(job.job_id)!.completed_at).toBe(completedAt)

      // Late fail
      jobManager.failJob(job.job_id, { code: 'LATE_CRASH', message: 'Crash after cancel' })
      expect(jobManager.getJob(job.job_id)!.status).toBe('cancelled')
    })

    it('prevents queue double-drain when terminal methods are called redundantly', () => {
      // Enqueue job 1 and job 2
      const job1 = jobManager.enqueue({ format: 'document', prompt: 'Job 1' })
      const job2 = jobManager.enqueue({ format: 'document', prompt: 'Job 2' })

      // Advance job 1 to generating
      job1.status = 'generating'
      ;(jobManager as any).activeJobId = job1.job_id

      const drainSpy = vi.spyOn(jobManager as any, 'drainQueue')

      // Complete job 1
      jobManager.completeJob(job1.job_id, null)
      expect(drainSpy).toHaveBeenCalledTimes(1)

      // Duplicate complete calls on job 1 must NOT trigger drainQueue again
      jobManager.completeJob(job1.job_id, null)
      jobManager.failJob(job1.job_id, { code: 'ERR', message: 'msg' })
      jobManager.finalizeCancellation(job1.job_id)
      expect(drainSpy).toHaveBeenCalledTimes(1)
    })
  })
})
