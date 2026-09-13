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
  isDestroyed: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  listeners: Map<string, (...args: any[]) => void>
}

interface FakeView {
  webContents: FakeWebContents
  setVisible: ReturnType<typeof vi.fn>
  setBounds: ReturnType<typeof vi.fn>
}

const { ipcMainHandlers, activeViews, createDocsView, createSlidesView, createSheetsView, createPdfView } = vi.hoisted(() => {
  let nextId = 100
  const activeViews: FakeView[] = []

  const makeView = () => {
    const listeners = new Map<string, (...args: any[]) => void>()
    const fakeWc = {
      id: nextId++,
      listeners,
      send: vi.fn(),
      once: vi.fn((event: string, handler: (...args: any[]) => void) => {
        listeners.set(event, handler)
      }),
      on: vi.fn((event: string, handler: (...args: any[]) => void) => {
        listeners.set(event, handler)
      }),
      isDestroyed: vi.fn(() => false),
      close: vi.fn(),
    }
    const view = {
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

const testSaveDir = join(tmpdir(), `genoffice-d72-test-${Date.now()}`)

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

describe('Native GenOffice Agent Invocation & Hidden Background WebContentsView (D7.2)', () => {
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

  async function createValidDocxBuffer(): Promise<Buffer> {
    const zip = new JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    zip.file('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>D7.2 Verified</w:t></w:r></w:p></w:body></w:document>')
    return zip.generateAsync({ type: 'nodebuffer' })
  }

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

  describe('AutomationViewManager — Hidden Viewport and Invariants', () => {
    it('allocates a hidden WebContentsView with standard bounds (1280x800) and setVisible(false)', async () => {
      const handle = await viewManager.createHiddenView('document')
      expect(handle).toBeDefined()
      expect(handle.format).toBe('document')
      expect(fakeWindow.contentView.addChildView).toHaveBeenCalledWith(handle.view)
      expect(handle.view.setBounds).toHaveBeenCalledWith({ x: 0, y: 0, width: 1280, height: 800 })
      expect(handle.view.setVisible).toHaveBeenCalledWith(false)
    })

    it('routes format to corresponding editor factory', async () => {
      await viewManager.createHiddenView('document')
      expect(createDocsView).toHaveBeenCalled()
      viewManager.destroyActiveView()

      await viewManager.createHiddenView('presentation')
      expect(createSlidesView).toHaveBeenCalled()
      viewManager.destroyActiveView()

      await viewManager.createHiddenView('spreadsheet')
      expect(createSheetsView).toHaveBeenCalledWith({ includeAiHandlers: false })
      viewManager.destroyActiveView()

      await viewManager.createHiddenView('pdf')
      expect(createPdfView).toHaveBeenCalled()
      viewManager.destroyActiveView()
    })

    it('enforces concurrency limit of 1 active hidden background view', async () => {
      await viewManager.createHiddenView('document')
      await expect(viewManager.createHiddenView('spreadsheet')).rejects.toThrow('CONCURRENCY_VIOLATION')
      viewManager.destroyActiveView()
    })

    it('cleanly destroys active view and removes from window content view', async () => {
      const handle = await viewManager.createHiddenView('document')
      expect(childViews.length).toBe(1)
      viewManager.destroyActiveView()
      expect(fakeWindow.contentView.removeChildView).toHaveBeenCalledWith(handle.view)
      expect(handle.view.webContents.close).toHaveBeenCalled()
      expect(viewManager.getActiveHandle()).toBeNull()
      expect(childViews.length).toBe(0)
    })
  })

  describe('AutomationExecutionRunner — Execution Lifecycle & Substates', () => {
    it('transitions through STARTING -> RUNNING_AGENT -> AGENT_COMPLETED and returns null for D7.2', async () => {
      const record: AutomationJobRecord = {
        job_id: 'job_test_substates_1',
        format: 'document',
        prompt: 'Generate an executive briefing',
        options: { title: 'Executive Summary', approx_pages: 2 },
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }
      ;(jobManager as any).jobs.set(record.job_id, record)

      const executePromise = runner.execute(record)

      // 1. Wait a tick for view creation and verify substate is STARTING
      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      expect(handle).not.toBeNull()
      const wc = handle!.view.webContents

      // Setup mock renderer to respond to start-agent with progress and done
      wc.send = vi.fn(async (channel: string, payload: any) => {
        if (channel === 'automation:start-agent') {
          // Report progress
          ipcMainHandlers.get('automation:agent-progress')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              current_turn: 2,
              max_turns: 100,
              last_tool: 'insert_content',
              message: 'Executing insert_content',
            },
          )
          // Report done
          ipcMainHandlers.get('automation:agent-done')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              ok: true,
              turns: 2,
              tools_executed: ['insert_content'],
              content_detected: true,
              content_signal: {
                before: 'empty (0 chars, size 2)',
                after: 'populated (773 chars, size 868)',
                detail: 'Document editor text length changed from 0 to 773 chars (content size: 2 -> 868)',
              },
            },
          )

          const docxBuf = await createValidDocxBuffer()
          const savedPath = join(testSaveDir, 'Executive Summary.docx')
          writeFileSync(savedPath, docxBuf)
          ipcMainHandlers.get('automation:file-saved')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              file_path: savedPath,
              file_format: 'document',
              title: 'Executive Summary',
            },
          )
        }
      })

      // Signal ready from renderer
      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: wc.id } }, { format: 'document' })

      const result = await executePromise
      expect(result).not.toBeNull()
      expect(result?.file_path).toBe(join(testSaveDir, 'Executive Summary.docx'))

      // Verify content changed signal was propagated to job record
      const job = jobManager.getJob(record.job_id)
      expect(job?.progress?.content_detected).toBe(true)
      expect(job?.progress?.content_signal?.before).toBe('empty (0 chars, size 2)')
      expect(job?.progress?.content_signal?.after).toBe('populated (773 chars, size 868)')
      expect(job?.progress?.content_signal?.before).not.toBe(job?.progress?.content_signal?.after)

      // Verify view is destroyed
      expect(viewManager.getActiveHandle()).toBeNull()
    })

    it('propagates real content-change signal for Slides (presentation format)', async () => {
      const record: AutomationJobRecord = {
        job_id: 'job_test_slides_content',
        format: 'presentation',
        prompt: 'Generate pitch deck',
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }
      ;(jobManager as any).jobs.set(record.job_id, record)

      const executePromise = runner.execute(record)
      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      const wc = handle!.view.webContents

      wc.send = vi.fn(async (channel: string) => {
        if (channel === 'automation:start-agent') {
          ipcMainHandlers.get('automation:agent-done')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              ok: true,
              turns: 4,
              tools_executed: ['generate_deck', 'apply_ops'],
              content_detected: true,
              content_signal: {
                before: 'slides: 1, elements: 0',
                after: 'slides: 2, elements: 4',
                detail: 'Slide deck elements/nodes: 0 -> 4 (slides: 1 -> 2)',
              },
            },
          )

          const pptxBuf = await createValidPptxBuffer()
          const savedPath = join(testSaveDir, 'Pitch Deck.pptx')
          writeFileSync(savedPath, pptxBuf)
          ipcMainHandlers.get('automation:file-saved')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              file_path: savedPath,
              file_format: 'presentation',
              title: 'Pitch Deck',
            },
          )
        }
      })

      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: wc.id } }, { format: 'presentation' })
      const result = await executePromise
      expect(result).not.toBeNull()

      const job = jobManager.getJob(record.job_id)
      expect(job?.progress?.content_detected).toBe(true)
      expect(job?.progress?.content_signal?.before).toBe('slides: 1, elements: 0')
      expect(job?.progress?.content_signal?.after).toBe('slides: 2, elements: 4')
      expect(job?.progress?.content_signal?.before).not.toBe(job?.progress?.content_signal?.after)
      expect(viewManager.getActiveHandle()).toBeNull()
    })

    it('propagates real content-change signal for Sheets (spreadsheet format)', async () => {
      const record: AutomationJobRecord = {
        job_id: 'job_test_sheets_content',
        format: 'spreadsheet',
        prompt: 'Create financial model',
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }
      ;(jobManager as any).jobs.set(record.job_id, record)

      const executePromise = runner.execute(record)
      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      const wc = handle!.view.webContents

      wc.send = vi.fn(async (channel: string) => {
        if (channel === 'automation:start-agent') {
          ipcMainHandlers.get('automation:agent-done')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              ok: true,
              turns: 3,
              tools_executed: ['set_range', 'format_range'],
              content_detected: true,
              content_signal: {
                before: 'cells: 0, journal: 0',
                after: 'cells: 42, journal: 2',
                detail: 'Workbook cells: 0 -> 42, edit journal entries: 0 -> 2',
              },
            },
          )

          const xlsxBuf = await createValidXlsxBuffer()
          const savedPath = join(testSaveDir, 'Financial Model.xlsx')
          writeFileSync(savedPath, xlsxBuf)
          ipcMainHandlers.get('automation:file-saved')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              file_path: savedPath,
              file_format: 'spreadsheet',
              title: 'Financial Model',
            },
          )
        }
      })

      ipcMainHandlers.get('automation:renderer-ready')?.({ sender: { id: wc.id } }, { format: 'spreadsheet' })
      const result = await executePromise
      expect(result).not.toBeNull()

      const job = jobManager.getJob(record.job_id)
      expect(job?.progress?.content_detected).toBe(true)
      expect(job?.progress?.content_signal?.before).toBe('cells: 0, journal: 0')
      expect(job?.progress?.content_signal?.after).toBe('cells: 42, journal: 2')
      expect(job?.progress?.content_signal?.before).not.toBe(job?.progress?.content_signal?.after)
      expect(viewManager.getActiveHandle()).toBeNull()
    })

    it('verifies local attachment existence and rejects unreadable/missing files', async () => {
      const nonExistentPath = join(tmpdir(), `missing_${Date.now()}.png`)

      const record: AutomationJobRecord = {
        job_id: 'job_test_att_missing',
        format: 'document',
        prompt: 'Summarize attachment',
        attachments: [
          {
            type: 'image',
            storage_ref: nonExistentPath,
            filename: 'missing.png',
          },
        ],
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }

      const executePromise = runner.execute(record)

      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      expect(handle).not.toBeNull()

      // Signal ready from renderer
      ipcMainHandlers.get('automation:renderer-ready')?.(
        { sender: { id: handle!.webContentsId } },
        { format: 'document' },
      )

      await expect(executePromise).rejects.toThrow('Local file not found')
      expect(viewManager.getActiveHandle()).toBeNull()
    })

    it('accepts existing local attachments and passes metadata to renderer', async () => {
      const tempFile = join(tmpdir(), `valid_att_${Date.now()}.txt`)
      writeFileSync(tempFile, 'Sample evidence content')

      try {
        const record: AutomationJobRecord = {
          job_id: 'job_test_att_valid',
          format: 'document',
          prompt: 'Analyze evidence',
          attachments: [
            {
              type: 'document',
              storage_ref: tempFile,
              filename: 'evidence.txt',
              size_bytes: 23,
            },
          ],
          status: 'generating',
          created_at: new Date().toISOString(),
          cancellation_requested: false,
          progress: null,
          artifact: null,
          error: null,
        }

        let sentStartPayload: any = null

        const executePromise = runner.execute(record)

        await new Promise((r) => setTimeout(r, 5))
        const handle = viewManager.getActiveHandle()
        expect(handle).not.toBeNull()
        const wc = handle!.view.webContents

        wc.send = vi.fn(async (channel: string, payload: any) => {
          if (channel === 'automation:start-agent') {
            sentStartPayload = payload
            ipcMainHandlers.get('automation:agent-done')?.(
              { sender: { id: wc.id } },
              {
                job_id: record.job_id,
                ok: true,
                turns: 1,
                tools_executed: ['read_file'],
                content_detected: true,
              },
            )

            const docxBuf = await createValidDocxBuffer()
            const savedPath = join(testSaveDir, 'Evidence Report.docx')
            writeFileSync(savedPath, docxBuf)
            ipcMainHandlers.get('automation:file-saved')?.(
              { sender: { id: wc.id } },
              {
                job_id: record.job_id,
                file_path: savedPath,
                file_format: 'document',
                title: 'Evidence Report',
              },
            )
          }
        })

        // Signal ready
        ipcMainHandlers.get('automation:renderer-ready')?.(
          { sender: { id: handle!.webContentsId } },
          { format: 'document' },
        )

        const result = await executePromise
        expect(result).not.toBeNull()
        expect(sentStartPayload).not.toBeNull()
        expect(sentStartPayload.attachments).toHaveLength(1)
        expect(sentStartPayload.attachments[0].storage_ref).toBe(tempFile)
      } finally {
        if (existsSync(tempFile)) unlinkSync(tempFile)
      }
    })

    it('handles cooperative cancellation by sending automation:agent-cancel to renderer', async () => {
      const record: AutomationJobRecord = {
        job_id: 'job_test_cancel',
        format: 'document',
        prompt: 'Long generation',
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }

      let cancelDispatched = false

      const executePromise = runner.execute(record)

      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      expect(handle).not.toBeNull()
      const wc = handle!.view.webContents

      wc.send = vi.fn((channel: string) => {
        if (channel === 'automation:agent-cancel') {
          cancelDispatched = true
        }
      })

      // Request cancellation
      record.cancellation_requested = true

      // Signal ready
      ipcMainHandlers.get('automation:renderer-ready')?.(
        { sender: { id: handle!.webContentsId } },
        { format: 'document' },
      )

      const result = await executePromise
      expect(result).toBeNull()
      expect(viewManager.getActiveHandle()).toBeNull()
    })

    it('handles renderer error signal cleanly and tears down hidden background view', async () => {
      const record: AutomationJobRecord = {
        job_id: 'job_test_error',
        format: 'presentation',
        prompt: 'Generate pitch deck',
        status: 'generating',
        created_at: new Date().toISOString(),
        cancellation_requested: false,
        progress: null,
        artifact: null,
        error: null,
      }

      const executePromise = runner.execute(record)

      await new Promise((r) => setTimeout(r, 5))
      const handle = viewManager.getActiveHandle()
      expect(handle).not.toBeNull()
      const wc = handle!.view.webContents

      wc.send = vi.fn((channel: string) => {
        if (channel === 'automation:start-agent') {
          ipcMainHandlers.get('automation:agent-error')?.(
            { sender: { id: wc.id } },
            {
              job_id: record.job_id,
              code: 'AGENT_LOOP_ERROR',
              message: 'Model API quota exceeded',
            },
          )
        }
      })

      // Signal ready
      ipcMainHandlers.get('automation:renderer-ready')?.(
        { sender: { id: handle!.webContentsId } },
        { format: 'presentation' },
      )

      await expect(executePromise).rejects.toThrow('Model API quota exceeded')
      expect(viewManager.getActiveHandle()).toBeNull()
    })
  })
})
