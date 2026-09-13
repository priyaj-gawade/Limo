import { existsSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { app } from 'electron'
import type { BrowserWindow, WebContentsView } from 'electron'
import { createDocsView, defaultSaveDir, markDocsNewBlank, uniquePathIn } from '../../../docs/src/main/docs-main'
import { createSlidesView } from '../../../slides/src/main/slides-main'
import { createSheetsView, queueWorkbookForView } from '../../../sheets/src/main/sheets-main'
import { blankXlsxBuffer } from '../../../sheets/src/gateway/csv-import'
import { createPdfView, markPdfUntitledPath } from '../../../pdf/src/main/pdf-main'
import { blankPdfBuffer } from '../../../pdf/src/main/blank-pdf'
import type { AutomationFormat } from './automation-types'
import { resolveSafeFileName } from './automation-file-validator'

export interface HiddenViewHandle {
  view: WebContentsView
  webContentsId: number
  format: AutomationFormat
  tempFilePath?: string
  backingFilePath?: string
  fileCommitted: boolean
  isCrashed?: boolean
  crashDetails?: { reason: string; exitCode: number }
}

/**
 * Manages hidden background WebContentsView instances dedicated to local automation execution.
 *
 * NOTE: This is a hidden background WebContentsView with an offscreen desktop viewport,
 * NOT true headless Chromium/Electron execution.
 *
 * Invariant Guarantees:
 * 1. View is NEVER registered with TabManager.tabs (no tab strip entry).
 * 2. TabManager.activateTab() is NEVER called (no window/OS focus stealing).
 * 3. view.setVisible(false) is strictly enforced (invisible offscreen execution).
 * 4. Viewport is given standard desktop dimensions (1280x800) so renderers that depend on
 *    layout metrics (ProseMirror, Konva/FIT_WIDTH, Univer virtual grid) calculate correctly.
 * 5. Background throttling is disabled so timer loops and async agent turns execute at full performance.
 * 6. Audio is muted so automated runs cannot play sounds.
 * 7. Concurrency is limited to 1 active view at any time.
 */
export class AutomationViewManager {
  private activeHandle: HiddenViewHandle | null = null

  constructor(private readonly shellWindow: BrowserWindow) {}

  public getActiveHandle(): HiddenViewHandle | null {
    return this.activeHandle
  }

  public getActiveWcId(): number | null {
    return this.activeHandle ? this.activeHandle.webContentsId : null
  }

  /**
   * Allocates a hidden background WebContentsView for the requested format.
   */
  public async createHiddenView(format: AutomationFormat, title?: string): Promise<HiddenViewHandle> {
    if (this.activeHandle) {
      throw new Error(`CONCURRENCY_VIOLATION: A hidden background view (${this.activeHandle.format}) is already active`)
    }

    let view: WebContentsView
    let tempFilePath: string | undefined
    let backingFilePath: string | undefined

    switch (format) {
      case 'document':
      case 'advisory':
      case 'summary':
        view = createDocsView(undefined)
        markDocsNewBlank(view.webContents.id)
        break
      case 'presentation':
        view = createSlidesView(undefined)
        break
      case 'spreadsheet': {
        const baseName = resolveSafeFileName('spreadsheet', title)
        const filePath = uniquePathIn(defaultSaveDir(), baseName)
        writeFileSync(filePath, await blankXlsxBuffer())
        view = createSheetsView({ includeAiHandlers: false })
        queueWorkbookForView(view.webContents, filePath)
        backingFilePath = filePath
        break
      }
      case 'pdf': {
        const baseName = resolveSafeFileName('pdf', title)
        const filePath = uniquePathIn(defaultSaveDir(), baseName)
        const buf = await blankPdfBuffer()
        writeFileSync(filePath, buf)
        markPdfUntitledPath(filePath)
        view = createPdfView(filePath)
        backingFilePath = filePath
        break
      }
      default:
        throw new Error(`UNSUPPORTED_FORMAT: Format '${format}' is not supported for hidden background execution`)
    }

    // Attach as hidden child view with standard desktop dimensions to prevent layout collapse
    this.shellWindow.contentView.addChildView(view)
    view.setBounds({ x: 0, y: 0, width: 1280, height: 800 })
    view.setVisible(false)

    // Invariant: disable background throttling so timers/agent loops do not stall when invisible
    if (typeof (view.webContents as unknown as { setBackgroundThrottling?: (allowed: boolean) => void }).setBackgroundThrottling === 'function') {
      ;(view.webContents as unknown as { setBackgroundThrottling: (allowed: boolean) => void }).setBackgroundThrottling(false)
    }

    // Invariant: audio muted so background automation never produces audible output
    if (typeof (view.webContents as unknown as { setAudioMuted?: (muted: boolean) => void }).setAudioMuted === 'function') {
      ;(view.webContents as unknown as { setAudioMuted: (muted: boolean) => void }).setAudioMuted(true)
    }

    if (typeof view.webContents.on === 'function') {
      view.webContents.on('will-navigate', (event, url) => {
        if (!url.startsWith('http://localhost') && !url.startsWith('file://')) {
          console.warn(`[Hidden View Renderer:${format}] Blocked external navigation to ${url}`)
          event.preventDefault()
        }
      })
      view.webContents.on('render-process-gone', (_e, details) => {
        console.error(`[Hidden View Renderer:${format}] RENDER PROCESS GONE: reason=${details.reason}, exitCode=${details.exitCode}`)
        if (this.activeHandle && this.activeHandle.webContentsId === view.webContents.id) {
          this.activeHandle.isCrashed = true
          this.activeHandle.crashDetails = { reason: details.reason, exitCode: details.exitCode }
        }
      })
      view.webContents.on('unresponsive', () => {
        console.warn(`[Hidden View Renderer:${format}] Renderer webContents became UNRESPONSIVE`)
      })
      view.webContents.on('console-message', (e) => {
        console.log(`[Hidden View Renderer:${format}] ${e.message}`)
      })
      view.webContents.on('did-fail-load', (_e, errorCode, errorDescription, validatedURL) => {
        console.error(`[Hidden View Renderer:${format}] FAILED TO LOAD: ${errorCode} ${errorDescription} (${validatedURL})`)
      })
      view.webContents.on('did-finish-load', () => {
        console.log(`[Hidden View Renderer:${format}] Finished load: ${view.webContents.getURL()}`)
      })
    }

    const handle: HiddenViewHandle = {
      view,
      webContentsId: view.webContents.id,
      format,
      tempFilePath,
      backingFilePath,
      fileCommitted: false,
    }
    this.activeHandle = handle

    return handle
  }

  /**
   * Cleanly detaches and closes the active hidden background view.
   * If a backing file was pre-allocated but never committed, it is safely unlinked.
   */
  public destroyActiveView(): void {
    if (!this.activeHandle) return
    const handle = this.activeHandle
    this.activeHandle = null // Immediately clear active handle so subsequent allocations are unblocked
    const { view, tempFilePath, backingFilePath, fileCommitted } = handle
    try {
      if (!this.shellWindow.isDestroyed()) {
        try {
          this.shellWindow.contentView.removeChildView(view)
        } catch {
          /* fail-safe */
        }
      }
      if (!view.webContents.isDestroyed()) {
        try {
          view.webContents.close()
        } catch {
          /* fail-safe */
        }
      }
    } catch {
      /* fail-safe teardown */
    } finally {
      if (tempFilePath) {
        try {
          unlinkSync(tempFilePath)
        } catch {
          /* fail-safe temp cleanup */
        }
      }
      if (backingFilePath && !fileCommitted) {
        try {
          if (existsSync(backingFilePath)) {
            unlinkSync(backingFilePath)
            console.log(`[AutomationViewManager] Unlinked uncommitted backing file: ${backingFilePath}`)
          }
        } catch (err) {
          console.warn(`[AutomationViewManager] Failed to unlink uncommitted backing file: ${backingFilePath}`, err)
        }
      }
    }
  }
}
