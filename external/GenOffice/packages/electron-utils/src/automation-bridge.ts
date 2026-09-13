import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'

export interface AutomationStartAgentPayload {
  job_id: string
  format: string
  instruction: string
  options?: Record<string, unknown>
  attachments?: Array<{
    type: string
    storage_ref: string
    filename: string
    mime_type?: string
    size_bytes?: number
    metadata?: Record<string, unknown>
  }>
}

export interface AutomationProgressPayload {
  job_id: string
  substate?: string
  current_turn: number
  max_turns: number
  last_tool?: string
  message?: string
}

export interface AutomationAgentDonePayload {
  job_id: string
  ok: true
  turns: number
  tools_executed: string[]
  content_detected: boolean
  content_signal?: {
    before?: string | number
    after?: string | number
    detail?: string
  }
}

export interface AutomationAgentErrorPayload {
  job_id: string
  code: string
  message: string
}

export interface AutomationFileSavedPayload {
  job_id: string
  file_path: string
  file_format: string
  title?: string
  metadata?: Record<string, unknown>
}

export interface AutomationBridge {
  signalReady: (format: string) => void
  onStartAgent: (handler: (payload: AutomationStartAgentPayload) => void) => () => void
  onCancelAgent: (handler: () => void) => () => void
  sendProgress: (progress: AutomationProgressPayload) => void
  sendDone: (result: AutomationAgentDonePayload) => void
  sendError: (error: AutomationAgentErrorPayload) => void
  sendCancelled: (payload: { job_id: string }) => void
  sendFileSaved: (payload: AutomationFileSavedPayload) => void
}

/**
 * Installs the standard automation bridge in the renderer process via contextBridge.
 * Available as window.automationBridge in isolated renderer contexts.
 */
export function installAutomationBridge(): void {
  const bridge: AutomationBridge = {
    signalReady: (format: string) => {
      ipcRenderer.send('automation:renderer-ready', { format })
    },
    onStartAgent: (handler) => {
      const listener = (_event: IpcRendererEvent, payload: AutomationStartAgentPayload) => {
        handler(payload)
      }
      ipcRenderer.on('automation:start-agent', listener)
      return () => ipcRenderer.removeListener('automation:start-agent', listener)
    },
    onCancelAgent: (handler) => {
      const listener = () => handler()
      ipcRenderer.on('automation:agent-cancel', listener)
      return () => ipcRenderer.removeListener('automation:agent-cancel', listener)
    },
    sendProgress: (progress) => {
      ipcRenderer.send('automation:agent-progress', progress)
    },
    sendDone: (result) => {
      ipcRenderer.send('automation:agent-done', result)
    },
    sendError: (error) => {
      ipcRenderer.send('automation:agent-error', error)
    },
    sendCancelled: (payload) => {
      ipcRenderer.send('automation:agent-cancelled', payload)
    },
    sendFileSaved: (payload) => {
      ipcRenderer.send('automation:file-saved', payload)
    },
  }

  contextBridge.exposeInMainWorld('automationBridge', bridge)
}
