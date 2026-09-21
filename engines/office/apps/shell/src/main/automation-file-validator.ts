import { createHash } from 'node:crypto'
import { existsSync, readFileSync, statSync } from 'node:fs'
import JSZip from 'jszip'
import { PDFDocument } from 'pdf-lib'
import type { AutomationFormat } from './automation-types'

export interface FileValidationResult {
  valid: boolean
  size_bytes: number
  sha256: string
  error?: string
  metadata?: Record<string, unknown>
}

// Minimum plausible byte sizes for non-corrupt documents (headers + minimal structural entries)
const MIN_DOCX_BYTES = 100
const MIN_PPTX_BYTES = 100
const MIN_XLSX_BYTES = 100
const MIN_PDF_BYTES = 100

/**
 * Sanitizes a raw user-supplied title string to produce a safe filesystem base name.
 * Strips directory separators, forbidden OS characters, control chars, and path traversal tokens.
 */
export function sanitizeTitle(rawTitle?: string): string {
  if (!rawTitle || typeof rawTitle !== 'string') return ''
  // Strip path traversal sequences like ../ or ..\
  let cleaned = rawTitle.replace(/(?:\.\.[/\\])+/g, '')
  // Replace illegal filename chars and directory separators with space
  cleaned = cleaned.replace(/[<>:"/\\|?*\x00-\x1F]/g, ' ')
  // Remove space immediately preceding a dot
  cleaned = cleaned.replace(/\s+\./g, '.')
  // Strip isolated dots
  cleaned = cleaned.replace(/(^|\s)\.+(\s|$)/g, ' ')
  // Collapse whitespace
  cleaned = cleaned.replace(/\s+/g, ' ').trim()
  if (/^\.*$/.test(cleaned) || cleaned.length === 0) return ''
  return cleaned.slice(0, 80)
}

/**
 * Returns a safe, deterministic filename with the proper extension for the given format.
 */
export function resolveSafeFileName(format: AutomationFormat, rawTitle?: string): string {
  const safe = sanitizeTitle(rawTitle)
  switch (format) {
    case 'document':
    case 'summary':
      return safe ? `${safe}.docx` : 'Untitled Document.docx'
    case 'presentation':
      return safe ? `${safe}.pptx` : 'Untitled Presentation.pptx'
    case 'spreadsheet':
      return safe ? `${safe}.xlsx` : 'Untitled Spreadsheet.xlsx'
    case 'pdf':
      return safe ? `${safe}.pdf` : 'Untitled PDF.pdf'
    default:
      return safe ? `${safe}.bin` : 'Untitled Document.bin'
  }
}

/**
 * Validates that a saved document file on disk exists, meets size requirements,
 * and passes structural integrity parsing (JSZip for OpenXML, pdf-lib for PDF).
 */
export async function validateSavedDocument(
  filePath: string,
  format: AutomationFormat,
): Promise<FileValidationResult> {
  if (!existsSync(filePath)) {
    return {
      valid: false,
      size_bytes: 0,
      sha256: '',
      error: `FILE_NOT_FOUND: File does not exist on disk at '${filePath}'`,
    }
  }

  let size = 0
  try {
    const st = statSync(filePath)
    size = st.size
  } catch (err) {
    return {
      valid: false,
      size_bytes: 0,
      sha256: '',
      error: `FILE_STAT_FAILED: Unable to read file stats: ${String(err)}`,
    }
  }

  if (size === 0) {
    return {
      valid: false,
      size_bytes: 0,
      sha256: '',
      error: 'EMPTY_FILE: Saved file has 0 bytes',
    }
  }

  let buffer: Buffer
  try {
    buffer = readFileSync(filePath)
  } catch (err) {
    return {
      valid: false,
      size_bytes: size,
      sha256: '',
      error: `FILE_READ_FAILED: Unable to read file content: ${String(err)}`,
    }
  }

  const sha256 = createHash('sha256').update(buffer).digest('hex')

  // Format-specific structural validation
  try {
    switch (format) {
      case 'document':
      case 'summary': {
        if (size < MIN_DOCX_BYTES) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: `TRUNCATED_DOCX: File size (${size} bytes) is below minimum valid size (${MIN_DOCX_BYTES} bytes)`,
          }
        }
        const zip = await JSZip.loadAsync(buffer)
        if (!zip.file('[Content_Types].xml')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_DOCX: Missing [Content_Types].xml in OpenXML archive',
          }
        }
        const docXml = zip.file('word/document.xml')
        if (!docXml) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_DOCX: Missing word/document.xml part in OpenXML archive',
          }
        }
        const xmlText = await docXml.async('string')
        if (!xmlText.includes('<w:body>') && !xmlText.includes('<w:document')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_DOCX: word/document.xml does not contain a valid <w:body> element',
          }
        }
        return {
          valid: true,
          size_bytes: size,
          sha256,
          metadata: {
            format: 'docx',
            openxml_valid: true,
            hasDocumentXml: true,
          },
        }
      }

      case 'presentation': {
        if (size < MIN_PPTX_BYTES) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: `TRUNCATED_PPTX: File size (${size} bytes) is below minimum valid size (${MIN_PPTX_BYTES} bytes)`,
          }
        }
        const zip = await JSZip.loadAsync(buffer)
        if (!zip.file('[Content_Types].xml')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_PPTX: Missing [Content_Types].xml in OpenXML archive',
          }
        }
        if (!zip.file('ppt/presentation.xml')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_PPTX: Missing ppt/presentation.xml in OpenXML archive',
          }
        }
        // At least one slide must exist
        const slideFiles = zip.file(/ppt\/slides\/slide[0-9]+\.xml/)
        if (slideFiles.length === 0) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_PPTX: No slide XML parts found in presentation',
          }
        }
        return {
          valid: true,
          size_bytes: size,
          sha256,
          metadata: {
            format: 'pptx',
            openxml_valid: true,
            hasPresentationXml: true,
            slideCount: slideFiles.length,
            slide_count: slideFiles.length,
          },
        }
      }

      case 'spreadsheet': {
        if (size < MIN_XLSX_BYTES) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: `TRUNCATED_XLSX: File size (${size} bytes) is below minimum valid size (${MIN_XLSX_BYTES} bytes)`,
          }
        }
        const zip = await JSZip.loadAsync(buffer)
        if (!zip.file('[Content_Types].xml')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_XLSX: Missing [Content_Types].xml in OpenXML archive',
          }
        }
        if (!zip.file('xl/workbook.xml')) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_XLSX: Missing xl/workbook.xml in OpenXML archive',
          }
        }
        const sheetFiles = zip.file(/xl\/worksheets\/sheet[0-9]+\.xml/)
        if (sheetFiles.length === 0) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_XLSX: No worksheet XML parts found in workbook',
          }
        }
        return {
          valid: true,
          size_bytes: size,
          sha256,
          metadata: {
            format: 'xlsx',
            openxml_valid: true,
            hasWorkbookXml: true,
            sheetCount: sheetFiles.length,
            sheet_count: sheetFiles.length,
          },
        }
      }

      case 'pdf': {
        if (size < MIN_PDF_BYTES) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: `TRUNCATED_PDF: File size (${size} bytes) is below minimum valid size (${MIN_PDF_BYTES} bytes)`,
          }
        }
        let pdfDoc: PDFDocument
        try {
          pdfDoc = await PDFDocument.load(buffer)
        } catch (err) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: `CORRUPT_PDF: pdf-lib failed to parse document structure: ${String(err)}`,
          }
        }
        const pageCount = pdfDoc.getPageCount()
        if (pageCount < 1) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_PDF: Document contains 0 pages',
          }
        }
        const page1 = pdfDoc.getPage(0)
        if (page1.getWidth() <= 0 || page1.getHeight() <= 0) {
          return {
            valid: false,
            size_bytes: size,
            sha256,
            error: 'INVALID_PDF: Page dimensions are invalid (width or height <= 0)',
          }
        }
        return {
          valid: true,
          size_bytes: size,
          sha256,
          metadata: {
            format: 'pdf',
            pdf_valid: true,
            pageCount,
            page_count: pageCount,
          },
        }
      }

      default:
        // Generic fallback for plain text / markdown / html
        return {
          valid: true,
          size_bytes: size,
          sha256,
          metadata: {
            format,
          },
        }
    }
  } catch (err) {
    return {
      valid: false,
      size_bytes: size,
      sha256,
      error: `STRUCTURAL_PARSE_ERROR: Failed to parse document structure: ${String(err)}`,
    }
  }
}
