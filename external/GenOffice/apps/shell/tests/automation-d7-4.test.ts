import { existsSync, mkdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import JSZip from 'jszip'
import { PDFDocument } from 'pdf-lib'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { AutomationJobManager } from '../src/main/automation-manager'
import { AutomationExecutionRunner } from '../src/main/automation-runner'
import { resolveSafeFileName, sanitizeTitle, validateSavedDocument } from '../src/main/automation-file-validator'
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

const testSaveDir = join(tmpdir(), `genoffice-d74-test-${Date.now()}`)

const {
  ipcMainHandlers,
  activeViews,
  createDocsView,
  createSlidesView,
  createSheetsView,
  createPdfView,
  queueWorkbookForView,
  markPdfUntitledPath,
  markDocsNewBlank,
} = vi.hoisted(() => {
  let nextId = 300
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
    queueWorkbookForView: vi.fn(),
    markPdfUntitledPath: vi.fn(),
    markDocsNewBlank: vi.fn(),
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

vi.mock('../../docs/src/main/docs-main', () => ({
  createDocsView: (...args: unknown[]) => createDocsView(...(args as [])),
  markDocsNewBlank: (...args: unknown[]) => markDocsNewBlank(...(args as [])),
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
  queueWorkbookForView: (...args: unknown[]) => queueWorkbookForView(...(args as [])),
}))

vi.mock('../../sheets/src/gateway/csv-import', () => ({
  blankXlsxBuffer: async () => {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('xl/workbook.xml', '<workbook/>')
    zip.file('xl/worksheets/sheet1.xml', '<worksheet/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  },
}))

vi.mock('../../pdf/src/main/pdf-main', () => ({
  createPdfView: (...args: unknown[]) => createPdfView(...(args as [])),
  markPdfUntitledPath: (...args: unknown[]) => markPdfUntitledPath(...(args as [])),
}))

vi.mock('../../pdf/src/main/blank-pdf', () => ({
  blankPdfBuffer: async () => {
    const doc = await PDFDocument.create()
    doc.addPage([600, 400])
    const bytes = await doc.save()
    return Buffer.from(bytes)
  },
}))

describe('D7.4 Content Verification & Native Document Saving/Export', () => {
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

  // Helper to create a valid minimal DOCX buffer
  async function createValidDocxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>D7.4 Verified Content</w:t></w:r></w:p></w:body></w:document>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

  // Helper to create a valid minimal PPTX buffer
  async function createValidPptxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('ppt/presentation.xml', '<presentation/>')
    zip.file('ppt/slides/slide1.xml', '<slide/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

  // Helper to create a valid minimal XLSX buffer
  async function createValidXlsxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('xl/workbook.xml', '<workbook/>')
    zip.file('xl/worksheets/sheet1.xml', '<worksheet/>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

  // Helper to create a valid minimal PDF buffer
  async function createValidPdfBuffer(): Promise<Buffer> {
    const doc = await PDFDocument.create()
    const page = doc.addPage([600, 400])
    page.drawText('D7.4 Validated PDF')
    const bytes = await doc.save()
    return Buffer.from(bytes)
  }

  describe('1. Content Rejection & Tool-Count Blind Trust Prevention', () => {
    it('fails job with ZERO_CONTENT_GENERATED when content_detected is false', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'document',
        prompt: 'Generate an empty document',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'document' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      // Signal agent done with content_detected: false
      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 2,
        tools_executed: ['read_document'],
        content_detected: false,
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('failed')
        expect(updated?.error?.code).toBe('ZERO_CONTENT_GENERATED')
        expect(viewManager.getActiveHandle()).toBeNull()
      })
    })

    it('rejects execution when agent only ran read-only tools without mutating document', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'pdf',
        prompt: 'Search keywords in PDF',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'pdf' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      // 8 tools executed, but zero mutations -> content_detected: false
      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 8,
        tools_executed: ['search_text', 'read_pages', 'search_text', 'list_attachments', 'get_outline'],
        content_detected: false,
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('failed')
        expect(updated?.error?.code).toBe('ZERO_CONTENT_GENERATED')
      })
    })
  })

  describe('2. Backing File Allocation & Tracking for Sheets & PDF', () => {
    it('allocates and queues backing .xlsx file in defaultSaveDir for spreadsheet format', async () => {
      const handle = await viewManager.createHiddenView('spreadsheet', 'Sales Report')
      expect(handle.backingFilePath).toBeDefined()
      expect(handle.backingFilePath?.endsWith('.xlsx')).toBe(true)
      expect(handle.fileCommitted).toBe(false)
      expect(existsSync(handle.backingFilePath!)).toBe(true)
      expect(queueWorkbookForView).toHaveBeenCalledWith(handle.view.webContents, handle.backingFilePath)

      // Cleanup
      viewManager.destroyActiveView()
      expect(existsSync(handle.backingFilePath!)).toBe(false) // Unlinked because not committed
    })

    it('allocates and marks backing .pdf file in defaultSaveDir for pdf format', async () => {
      const handle = await viewManager.createHiddenView('pdf', 'Contract Note')
      expect(handle.backingFilePath).toBeDefined()
      expect(handle.backingFilePath?.endsWith('.pdf')).toBe(true)
      expect(handle.fileCommitted).toBe(false)
      expect(existsSync(handle.backingFilePath!)).toBe(true)
      expect(markPdfUntitledPath).toHaveBeenCalledWith(handle.backingFilePath)

      // Cleanup
      viewManager.destroyActiveView()
      expect(existsSync(handle.backingFilePath!)).toBe(false) // Unlinked because not committed
    })
  })

  describe('3. Backing File Cleanup on All Failure Paths', () => {
    it('unlinks uncommitted backing .xlsx file when Sheets execution fails', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'spreadsheet',
        prompt: 'Populate inventory sheet',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const handle = viewManager.getActiveHandle()!
      const backingPath = handle.backingFilePath!
      expect(existsSync(backingPath)).toBe(true)

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'spreadsheet' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      // Renderer sends agent error
      ipcMainHandlers.get('automation:agent-error')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        code: 'AGENT_CRASH',
        message: 'Fatal error in worker',
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('failed')
        expect(existsSync(backingPath)).toBe(false) // Verified unlinked
      })
    })

    it('unlinks uncommitted backing .pdf file when PDF content verification fails', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'pdf',
        prompt: 'Check PDF',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const handle = viewManager.getActiveHandle()!
      const backingPath = handle.backingFilePath!
      expect(existsSync(backingPath)).toBe(true)

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'pdf' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 1,
        tools_executed: [],
        content_detected: false,
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('failed')
        expect(existsSync(backingPath)).toBe(false) // Verified unlinked
      })
    })

    it('unlinks backing file when native save fails with SAVE_EXECUTION_FAILED', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'spreadsheet',
        prompt: 'Build financial model',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const handle = viewManager.getActiveHandle()!
      const backingPath = handle.backingFilePath!
      expect(existsSync(backingPath)).toBe(true)

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'spreadsheet' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 2,
        tools_executed: ['set_cells'],
        content_detected: true,
      })

      // Renderer reports save execution failure
      ipcMainHandlers.get('automation:agent-error')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        code: 'SAVE_EXECUTION_FAILED',
        message: 'Disk full or permissions error',
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('failed')
        expect(updated?.error?.code).toBe('SAVE_EXECUTION_FAILED')
        expect(existsSync(backingPath)).toBe(false)
      })
    })
  })

  describe('4. PDF Dual-Pathway Resolution', () => {
    it('Pathway B (Standalone create_document): commits standalone PDF and unlinks blank backing PDF', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'pdf',
        prompt: 'Generate an executive summary report',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const handle = viewManager.getActiveHandle()!
      const blankBackingPath = handle.backingFilePath!
      expect(existsSync(blankBackingPath)).toBe(true)

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'pdf' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      // Simulate createAiDocument creating standalone file
      const standalonePath = join(testSaveDir, 'Executive Report.pdf')
      const standaloneBuffer = await createValidPdfBuffer()
      writeFileSync(standalonePath, standaloneBuffer)

      // AgentLoop finishes with standalone path
      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 1,
        tools_executed: ['create_document'],
        content_detected: true,
      })

      ipcMainHandlers.get('automation:file-saved')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        file_path: standalonePath,
        file_format: 'pdf',
        title: 'Executive Report',
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('completed')
        expect(updated?.artifact?.file_path).toBe(standalonePath)
        expect(existsSync(standalonePath)).toBe(true)
        expect(existsSync(blankBackingPath)).toBe(false) // Blank backing file unlinked!
      })
    })

    it('Pathway A (In-Place Modifications): commits backing PDF as final artifact when saved', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'pdf',
        prompt: 'Annotate active PDF with remarks',
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const handle = viewManager.getActiveHandle()!
      const backingPath = handle.backingFilePath!
      expect(existsSync(backingPath)).toBe(true)

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'pdf' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      // In-place edits written to backingPath
      const updatedPdfBuffer = await createValidPdfBuffer()
      writeFileSync(backingPath, updatedPdfBuffer)

      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 2,
        tools_executed: ['insert_text'],
        content_detected: true,
      })

      ipcMainHandlers.get('automation:file-saved')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        file_path: backingPath,
        file_format: 'pdf',
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('completed')
        expect(updated?.artifact?.file_path).toBe(backingPath)
        expect(existsSync(backingPath)).toBe(true)
      })
    })
  })

  describe('5. Structural File Integrity Verification (OpenXML & pdf-lib)', () => {
    it('validates genuine DOCX file and returns SHA-256 digest', async () => {
      const docxPath = join(testSaveDir, 'test-valid.docx')
      const docxBuf = await createValidDocxBuffer()
      writeFileSync(docxPath, docxBuf)

      const res = await validateSavedDocument(docxPath, 'document')
      expect(res.valid).toBe(true)
      expect(res.size_bytes).toBe(docxBuf.length)
      expect(res.sha256).toHaveLength(64)
      expect(res.metadata?.hasDocumentXml).toBe(true)
    })

    it('rejects corrupt/truncated DOCX file and unlinks it', async () => {
      const corruptPath = join(testSaveDir, 'test-corrupt.docx')
      writeFileSync(corruptPath, Buffer.from('This is not a zip file at all!'))

      const res = await validateSavedDocument(corruptPath, 'document')
      expect(res.valid).toBe(false)
      expect(res.error).toBeDefined()
    })

    it('validates genuine PPTX file with presentation.xml and slide1.xml', async () => {
      const pptxPath = join(testSaveDir, 'test-valid.pptx')
      const pptxBuf = await createValidPptxBuffer()
      writeFileSync(pptxPath, pptxBuf)

      const res = await validateSavedDocument(pptxPath, 'presentation')
      expect(res.valid).toBe(true)
      expect(res.metadata?.hasPresentationXml).toBe(true)
    })

    it('validates genuine XLSX file with workbook.xml and sheet1.xml', async () => {
      const xlsxPath = join(testSaveDir, 'test-valid.xlsx')
      const xlsxBuf = await createValidXlsxBuffer()
      writeFileSync(xlsxPath, xlsxBuf)

      const res = await validateSavedDocument(xlsxPath, 'spreadsheet')
      expect(res.valid).toBe(true)
      expect(res.metadata?.hasWorkbookXml).toBe(true)
    })

    it('validates genuine PDF file using pdf-lib', async () => {
      const pdfPath = join(testSaveDir, 'test-valid.pdf')
      const pdfBuf = await createValidPdfBuffer()
      writeFileSync(pdfPath, pdfBuf)

      const res = await validateSavedDocument(pdfPath, 'pdf')
      expect(res.valid).toBe(true)
      expect(res.metadata?.pageCount).toBe(1)
    })
  })

  describe('6. Title Sanitization & Path Non-Collision', () => {
    it('sanitizes titles with reserved characters and path traversal', () => {
      expect(sanitizeTitle('../../evil:name*?.doc')).toBe('evil name.doc')
      expect(sanitizeTitle('Normal Document Title')).toBe('Normal Document Title')
      expect(sanitizeTitle('..')).toBe('')
      expect(sanitizeTitle('')).toBe('')
    })

    it('resolves safe file names per format', () => {
      expect(resolveSafeFileName('document', 'My Doc')).toBe('My Doc.docx')
      expect(resolveSafeFileName('presentation', undefined)).toBe('Untitled Presentation.pptx')
      expect(resolveSafeFileName('spreadsheet', 'Finance')).toBe('Finance.xlsx')
      expect(resolveSafeFileName('pdf', '<Illegal*Name>')).toBe('Illegal Name.pdf')
    })
  })

  describe('7. End-to-End D7.4 Happy Path Progression', () => {
    it('progresses through AGENT_COMPLETED -> CONTENT_VERIFIED -> SAVE_STARTED -> FILE_SAVED -> FILE_VALIDATED and returns AutomationArtifact', async () => {
      jobManager.setRunner(runner.getRunner())
      const job = jobManager.enqueue({
        format: 'document',
        prompt: 'Write an executive brief',
        options: { title: 'Executive Brief' },
      })

      await vi.waitFor(() => {
        expect(activeViews.length).toBe(1)
      })

      const currentView = activeViews[0]
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: currentView.webContents.id } }, { format: 'document' })

      await vi.waitFor(() => {
        expect(currentView.webContents.send).toHaveBeenCalledWith('automation:start-agent', expect.anything())
      })

      const docxPath = join(testSaveDir, 'Executive Brief.docx')
      const docxBuf = await createValidDocxBuffer()
      writeFileSync(docxPath, docxBuf)

      // 1. Agent completes
      ipcMainHandlers.get('automation:agent-done')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        ok: true,
        turns: 3,
        tools_executed: ['write_section', 'format_headings'],
        content_detected: true,
        content_signal: { before: '0 chars', after: '250 chars' },
      })

      // 2. Native save resolves
      ipcMainHandlers.get('automation:file-saved')?.({ sender: { id: currentView.webContents.id } }, {
        job_id: job.job_id,
        file_path: docxPath,
        file_format: 'document',
        title: 'Executive Brief',
      })

      await vi.waitFor(() => {
        const updated = jobManager.getJob(job.job_id)
        expect(updated?.status).toBe('completed')
        expect(updated?.progress?.substate).toBe('FILE_VALIDATED')
        expect(updated?.artifact).not.toBeNull()
        expect(updated?.artifact?.file_path).toBe(docxPath)
        expect(updated?.artifact?.title).toBe('Executive Brief')
        expect(updated?.artifact?.content_hash).toBeDefined()
        expect(viewManager.getActiveHandle()).toBeNull()
      })
    })
  })
})
