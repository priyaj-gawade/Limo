import type { IncomingMessage } from 'node:http'
import {
  MAX_TIMEOUT_SECONDS,
  MIN_TIMEOUT_SECONDS,
  type AutomationAttachmentReference,
  type AutomationAttachmentType,
  type AutomationError,
  type AutomationFormat,
  type AutomationGenerateOptions,
  type AutomationGenerateRequest,
} from './automation-types'

export const MAX_REQUEST_BODY_BYTES = 1024 * 1024 // 1 MB

export const SUPPORTED_FORMATS: ReadonlySet<AutomationFormat> = new Set([
  'document',
  'presentation',
  'spreadsheet',
  'pdf',
  'markdown',
  'html',
  'advisory',
  'summary',
])

export const SUPPORTED_ATTACHMENT_TYPES: ReadonlySet<AutomationAttachmentType> = new Set([
  'image',
  'document',
  'spreadsheet',
  'pdf',
  'audio',
  'video',
])

const TOP_LEVEL_ALLOWED_FIELDS = new Set([
  'format',
  'type',
  'prompt',
  'job_id',
  'project_id',
  'session_id',
  'canonical_id',
  'canonical_hash',
  'options',
  'request_id',
  'attachments',
])

const OPTIONS_ALLOWED_FIELDS = new Set([
  'title',
  'approx_pages',
  'theme',
  'audience',
  'tone',
  'detail_level',
  'save_directory',
  'sections_outline',
  'timeout_seconds',
  'timeout_ms',
  'max_turns',
  'custom_metadata',
])

const ATTACHMENT_ALLOWED_FIELDS = new Set([
  'type',
  'storage_ref',
  'filename',
  'mime_type',
  'size_bytes',
  'metadata',
])

export interface ValidationSuccess<T> {
  ok: true
  value: T
}

export interface ValidationFailure {
  ok: false
  status: number
  error: AutomationError
}

export type ValidationResult<T> = ValidationSuccess<T> | ValidationFailure

/**
 * Reads request stream up to maxBytes and parses JSON.
 * Returns 413 if body exceeds maxBytes, or 400 if invalid JSON.
 */
export async function parseJsonWithLimit(
  req: IncomingMessage,
  maxBytes: number = MAX_REQUEST_BODY_BYTES,
): Promise<ValidationResult<unknown>> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = []
    let totalBytes = 0
    let exceeded = false

    req.on('data', (chunk: Buffer) => {
      if (exceeded) return
      totalBytes += chunk.length
      if (totalBytes > maxBytes) {
        exceeded = true
        req.resume()
        resolve({
          ok: false,
          status: 413,
          error: {
            code: 'PAYLOAD_TOO_LARGE',
            message: `Request body exceeded maximum limit of ${maxBytes} bytes`,
          },
        })
        return
      }
      chunks.push(chunk)
    })

    req.on('end', () => {
      if (exceeded) return

      if (chunks.length === 0) {
        resolve({
          ok: false,
          status: 400,
          error: {
            code: 'EMPTY_BODY',
            message: 'Request body cannot be empty; JSON payload expected',
          },
        })
        return
      }

      const bodyStr = Buffer.concat(chunks).toString('utf8')
      try {
        const parsed = JSON.parse(bodyStr)
        resolve({ ok: true, value: parsed })
      } catch (err) {
        resolve({
          ok: false,
          status: 400,
          error: {
            code: 'INVALID_JSON',
            message: `Malformed JSON payload: ${err instanceof Error ? err.message : String(err)}`,
          },
        })
      }
    })

    req.on('error', (err) => {
      if (exceeded) return
      resolve({
        ok: false,
        status: 400,
        error: {
          code: 'STREAM_ERROR',
          message: `Request stream error: ${err.message}`,
        },
      })
    })
  })
}

/**
 * Validates incoming POST /api/v1/generate request payload.
 * Rejects unrecognized top-level and options fields with 400.
 */
export function validateGenerateRequest(
  body: unknown,
): ValidationResult<AutomationGenerateRequest> {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return {
      ok: false,
      status: 400,
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Request payload must be a JSON object',
      },
    }
  }

  const raw = body as Record<string, unknown>

  // 1. Check for unrecognized top-level fields
  for (const key of Object.keys(raw)) {
    if (!TOP_LEVEL_ALLOWED_FIELDS.has(key)) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: `Unrecognized field '${key}' in request payload`,
          field: key,
        },
      }
    }
  }

  // 2. format / type
  const rawFormat = (raw.format ?? raw.type) as unknown
  if (typeof rawFormat !== 'string' || !SUPPORTED_FORMATS.has(rawFormat as AutomationFormat)) {
    return {
      ok: false,
      status: 400,
      error: {
        code: 'VALIDATION_ERROR',
        message: `Field 'format' is required and must be one of: ${Array.from(SUPPORTED_FORMATS).join(', ')}`,
        field: 'format',
      },
    }
  }
  const format = rawFormat as AutomationFormat

  // 3. prompt
  if (typeof raw.prompt !== 'string') {
    return {
      ok: false,
      status: 400,
      error: {
        code: 'VALIDATION_ERROR',
        message: "Field 'prompt' is required and must be a string",
        field: 'prompt',
      },
    }
  }
  const trimmedPrompt = raw.prompt.trim()
  if (trimmedPrompt.length === 0) {
    return {
      ok: false,
      status: 400,
      error: {
        code: 'VALIDATION_ERROR',
        message: "Field 'prompt' must not be empty",
        field: 'prompt',
      },
    }
  }
  if (trimmedPrompt.length > 50000) {
    return {
      ok: false,
      status: 400,
      error: {
        code: 'VALIDATION_ERROR',
        message: "Field 'prompt' exceeds maximum length of 50000 characters",
        field: 'prompt',
      },
    }
  }

  // 4. job_id
  let jobId: string | undefined
  if (raw.job_id !== undefined && raw.job_id !== null) {
    if (typeof raw.job_id !== 'string') {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'job_id' must be a string",
          field: 'job_id',
        },
      }
    }
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(raw.job_id)) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'job_id' must match regex /^[a-zA-Z0-9_-]{1,128}$/",
          field: 'job_id',
        },
      }
    }
    jobId = raw.job_id
  }

  // 5. request_id
  let requestId: string | undefined
  if (raw.request_id !== undefined && raw.request_id !== null) {
    if (typeof raw.request_id !== 'string' || raw.request_id.length > 128) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'request_id' must be a string <= 128 characters",
          field: 'request_id',
        },
      }
    }
    requestId = raw.request_id
  }

  // 6. project_id
  let projectId: string | undefined
  if (raw.project_id !== undefined && raw.project_id !== null) {
    if (typeof raw.project_id !== 'string' || raw.project_id.length > 128) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'project_id' must be a string <= 128 characters",
          field: 'project_id',
        },
      }
    }
    projectId = raw.project_id
  }

  // 7. session_id
  let sessionId: string | undefined
  if (raw.session_id !== undefined && raw.session_id !== null) {
    if (typeof raw.session_id !== 'string' || raw.session_id.length > 128) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'session_id' must be a string <= 128 characters",
          field: 'session_id',
        },
      }
    }
    sessionId = raw.session_id
  }

  // 8. canonical_id
  let canonicalId: string | undefined
  if (raw.canonical_id !== undefined && raw.canonical_id !== null) {
    if (typeof raw.canonical_id !== 'string' || raw.canonical_id.length > 128) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'canonical_id' must be a string <= 128 characters",
          field: 'canonical_id',
        },
      }
    }
    canonicalId = raw.canonical_id
  }

  // 9. canonical_hash
  let canonicalHash: string | undefined
  if (raw.canonical_hash !== undefined && raw.canonical_hash !== null) {
    if (typeof raw.canonical_hash !== 'string' || !/^[a-fA-F0-9]{64}$/.test(raw.canonical_hash)) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'canonical_hash' must be a 64-character hex string",
          field: 'canonical_hash',
        },
      }
    }
    canonicalHash = raw.canonical_hash
  }

  // 10. options
  let options: AutomationGenerateOptions | undefined
  if (raw.options !== undefined && raw.options !== null) {
    if (typeof raw.options !== 'object' || Array.isArray(raw.options)) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'options' must be an object",
          field: 'options',
        },
      }
    }

    const rawOpt = raw.options as Record<string, unknown>
    for (const optKey of Object.keys(rawOpt)) {
      if (!OPTIONS_ALLOWED_FIELDS.has(optKey)) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Unrecognized option '${optKey}' in options object`,
            field: `options.${optKey}`,
          },
        }
      }
    }

    // Validate specific options fields
    if (rawOpt.title !== undefined && rawOpt.title !== null) {
      if (typeof rawOpt.title !== 'string' || rawOpt.title.length > 256) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.title' must be a string <= 256 characters",
            field: 'options.title',
          },
        }
      }
    }

    if (rawOpt.approx_pages !== undefined && rawOpt.approx_pages !== null) {
      if (
        typeof rawOpt.approx_pages !== 'number' ||
        !Number.isInteger(rawOpt.approx_pages) ||
        rawOpt.approx_pages < 1 ||
        rawOpt.approx_pages > 100
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.approx_pages' must be an integer between 1 and 100",
            field: 'options.approx_pages',
          },
        }
      }
    }

    if (rawOpt.save_directory !== undefined && rawOpt.save_directory !== null) {
      if (typeof rawOpt.save_directory !== 'string') {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.save_directory' must be a string path",
            field: 'options.save_directory',
          },
        }
      }
    }

    if (rawOpt.sections_outline !== undefined && rawOpt.sections_outline !== null) {
      if (
        !Array.isArray(rawOpt.sections_outline) ||
        rawOpt.sections_outline.some((item) => typeof item !== 'string')
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.sections_outline' must be an array of strings",
            field: 'options.sections_outline',
          },
        }
      }
    }

    if (rawOpt.timeout_seconds !== undefined && rawOpt.timeout_seconds !== null) {
      if (
        typeof rawOpt.timeout_seconds !== 'number' ||
        !Number.isInteger(rawOpt.timeout_seconds) ||
        rawOpt.timeout_seconds < MIN_TIMEOUT_SECONDS ||
        rawOpt.timeout_seconds > MAX_TIMEOUT_SECONDS
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'INVALID_TIMEOUT_RANGE',
            message: `Field 'options.timeout_seconds' must be an integer between ${MIN_TIMEOUT_SECONDS} and ${MAX_TIMEOUT_SECONDS}`,
            field: 'options.timeout_seconds',
          },
        }
      }
    }

    if (rawOpt.timeout_ms !== undefined && rawOpt.timeout_ms !== null) {
      if (typeof rawOpt.timeout_ms !== 'number' || rawOpt.timeout_ms <= 0) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.timeout_ms' must be a positive number",
            field: 'options.timeout_ms',
          },
        }
      }
    }

    if (rawOpt.max_turns !== undefined && rawOpt.max_turns !== null) {
      if (typeof rawOpt.max_turns !== 'number' || !Number.isInteger(rawOpt.max_turns) || rawOpt.max_turns < 1) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.max_turns' must be a positive integer",
            field: 'options.max_turns',
          },
        }
      }
    }

    if (rawOpt.custom_metadata !== undefined && rawOpt.custom_metadata !== null) {
      if (typeof rawOpt.custom_metadata !== 'object' || Array.isArray(rawOpt.custom_metadata)) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: "Field 'options.custom_metadata' must be an object",
            field: 'options.custom_metadata',
          },
        }
      }
    }

    options = rawOpt as unknown as AutomationGenerateOptions
  }

  // 11. attachments (optional reference array)
  let attachments: AutomationAttachmentReference[] | undefined
  if (raw.attachments !== undefined && raw.attachments !== null) {
    if (!Array.isArray(raw.attachments)) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'attachments' must be an array",
          field: 'attachments',
        },
      }
    }

    if (raw.attachments.length > 50) {
      return {
        ok: false,
        status: 400,
        error: {
          code: 'VALIDATION_ERROR',
          message: "Field 'attachments' exceeds maximum limit of 50 items",
          field: 'attachments',
        },
      }
    }

    const validatedAttachments: AutomationAttachmentReference[] = []

    for (let i = 0; i < raw.attachments.length; i++) {
      const item = raw.attachments[i]
      if (typeof item !== 'object' || item === null || Array.isArray(item)) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} must be an object`,
            field: `attachments[${i}]`,
          },
        }
      }

      const rawAtt = item as Record<string, unknown>

      // Check unknown fields in attachment object
      for (const attKey of Object.keys(rawAtt)) {
        if (!ATTACHMENT_ALLOWED_FIELDS.has(attKey)) {
          return {
            ok: false,
            status: 400,
            error: {
              code: 'VALIDATION_ERROR',
              message: `Unrecognized field '${attKey}' in attachment at index ${i}`,
              field: `attachments[${i}].${attKey}`,
            },
          }
        }
      }

      // type
      if (
        typeof rawAtt.type !== 'string' ||
        !SUPPORTED_ATTACHMENT_TYPES.has(rawAtt.type as AutomationAttachmentType)
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} requires 'type' to be one of: ${Array.from(
              SUPPORTED_ATTACHMENT_TYPES,
            ).join(', ')}`,
            field: `attachments[${i}].type`,
          },
        }
      }
      const attType = rawAtt.type as AutomationAttachmentType

      // storage_ref
      if (typeof rawAtt.storage_ref !== 'string' || rawAtt.storage_ref.trim().length === 0) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} requires a non-empty string 'storage_ref'`,
            field: `attachments[${i}].storage_ref`,
          },
        }
      }
      const storageRef = rawAtt.storage_ref.trim()
      if (storageRef.length > 1024) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} 'storage_ref' exceeds maximum length of 1024 characters`,
            field: `attachments[${i}].storage_ref`,
          },
        }
      }
      // Path traversal and null byte security check
      if (
        storageRef.includes('\0') ||
        storageRef.includes('..') ||
        /(^|[/\\])\.\.([/\\]|$)/.test(storageRef)
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} 'storage_ref' contains unsafe path traversal sequences`,
            field: `attachments[${i}].storage_ref`,
          },
        }
      }

      // filename
      if (typeof rawAtt.filename !== 'string' || rawAtt.filename.trim().length === 0) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} requires a non-empty string 'filename'`,
            field: `attachments[${i}].filename`,
          },
        }
      }
      const filename = rawAtt.filename.trim()
      if (filename.length > 255) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} 'filename' exceeds maximum length of 255 characters`,
            field: `attachments[${i}].filename`,
          },
        }
      }
      if (
        filename.includes('/') ||
        filename.includes('\\') ||
        filename.includes('\0') ||
        filename.includes('..')
      ) {
        return {
          ok: false,
          status: 400,
          error: {
            code: 'VALIDATION_ERROR',
            message: `Attachment at index ${i} 'filename' must not contain directory separators or traversal`,
            field: `attachments[${i}].filename`,
          },
        }
      }

      // mime_type
      let mimeType: string | undefined
      if (rawAtt.mime_type !== undefined && rawAtt.mime_type !== null) {
        if (typeof rawAtt.mime_type !== 'string' || rawAtt.mime_type.length > 128) {
          return {
            ok: false,
            status: 400,
            error: {
              code: 'VALIDATION_ERROR',
              message: `Attachment at index ${i} 'mime_type' must be a string <= 128 characters`,
              field: `attachments[${i}].mime_type`,
            },
          }
        }
        if (!/^[a-zA-Z0-9_\-+.]+\/[a-zA-Z0-9_\-+.]+$/.test(rawAtt.mime_type)) {
          return {
            ok: false,
            status: 400,
            error: {
              code: 'VALIDATION_ERROR',
              message: `Attachment at index ${i} 'mime_type' has invalid format`,
              field: `attachments[${i}].mime_type`,
            },
          }
        }
        mimeType = rawAtt.mime_type
      }

      // size_bytes
      let sizeBytes: number | undefined
      if (rawAtt.size_bytes !== undefined && rawAtt.size_bytes !== null) {
        if (
          typeof rawAtt.size_bytes !== 'number' ||
          !Number.isInteger(rawAtt.size_bytes) ||
          rawAtt.size_bytes < 0
        ) {
          return {
            ok: false,
            status: 400,
            error: {
              code: 'VALIDATION_ERROR',
              message: `Attachment at index ${i} 'size_bytes' must be a non-negative integer`,
              field: `attachments[${i}].size_bytes`,
            },
          }
        }
        sizeBytes = rawAtt.size_bytes
      }

      // metadata
      let metadata: Record<string, unknown> | undefined
      if (rawAtt.metadata !== undefined && rawAtt.metadata !== null) {
        if (typeof rawAtt.metadata !== 'object' || Array.isArray(rawAtt.metadata)) {
          return {
            ok: false,
            status: 400,
            error: {
              code: 'VALIDATION_ERROR',
              message: `Attachment at index ${i} 'metadata' must be an object`,
              field: `attachments[${i}].metadata`,
            },
          }
        }
        metadata = rawAtt.metadata as Record<string, unknown>
      }

      validatedAttachments.push({
        type: attType,
        storage_ref: storageRef,
        filename,
        ...(mimeType ? { mime_type: mimeType } : {}),
        ...(sizeBytes !== undefined ? { size_bytes: sizeBytes } : {}),
        ...(metadata ? { metadata } : {}),
      })
    }

    attachments = validatedAttachments
  }

  const validated: AutomationGenerateRequest = {
    format,
    prompt: trimmedPrompt,
    ...(jobId ? { job_id: jobId } : {}),
    ...(requestId ? { request_id: requestId } : {}),
    ...(projectId ? { project_id: projectId } : {}),
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(canonicalId ? { canonical_id: canonicalId } : {}),
    ...(canonicalHash ? { canonical_hash: canonicalHash } : {}),
    ...(options ? { options } : {}),
    ...(attachments ? { attachments } : {}),
  }

  return {
    ok: true,
    value: validated,
  }
}
