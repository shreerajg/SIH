import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  FileText,
  FileWarning,
  Image as ImageIcon,
  Loader2,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { UploadCategory, UploadedEvidence } from '@/lib/types'
import { UPLOAD_CATEGORY_LABELS, formatBytes, formatDate } from '@/lib/format'

const CATEGORY_OPTIONS: UploadCategory[] = [
  'test_report',
  'certificate',
  'datasheet',
  'product_label',
  'technical_document',
  'other',
]

const ACCEPT = '.pdf,.txt,.png,.jpg,.jpeg,application/pdf,text/plain,image/png,image/jpeg'

/**
 * Guess a document type from the file name. The guess only becomes the upload
 * category when a real signal is present — the returned `category` still drives
 * the backend's evidence_type (which gates matching), so we never silently
 * downgrade a test report to "other". When nothing matches, `confident` is
 * false and the UI asks the user how to classify it.
 */
function inferCategory(filename: string): { category: UploadCategory; confident: boolean } {
  const n = filename.toLowerCase()
  if (/(test|report|astm|\biec\b|type[\s_-]?test)/.test(n)) return { category: 'test_report', confident: true }
  if (/(cert|certificate|\bcoc\b|batch|material)/.test(n)) return { category: 'certificate', confident: true }
  if (/(label|marking|artwork|rating|nameplate)/.test(n)) return { category: 'product_label', confident: true }
  if (/(manual|datasheet|data[\s_-]?sheet|drawing|design|construction|technical|spec)/.test(n))
    return { category: 'technical_document', confident: true }
  return { category: 'other', confident: false }
}

/** Human wording for an extraction status. */
const STATUS_META: Record<string, { label: string; chip: string }> = {
  extracted: { label: 'Text read', chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' },
  pdf_has_no_text_layer: {
    label: 'Scanned PDF — no text',
    chip: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  },
  image_requires_ocr: {
    label: 'Image — not text-read',
    chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200',
  },
  extraction_failed: {
    label: 'Could not read',
    chip: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  },
  none: { label: 'Stored', chip: 'bg-ink-100 text-ink-600 ring-1 ring-ink-200' },
}

function statusMeta(status: string) {
  return STATUS_META[status] ?? STATUS_META.none
}

function FileIcon({ item }: { item: UploadedEvidence }) {
  if (item.content_type.startsWith('image/')) return <ImageIcon className="h-4 w-4" />
  if (item.extraction_status === 'extraction_failed' || item.extraction_status === 'pdf_has_no_text_layer')
    return <FileWarning className="h-4 w-4" />
  return <FileText className="h-4 w-4" />
}

/**
 * Upload and inspect product evidence documents.
 *
 * Files go to the product-evidence collection, which is separate from the
 * standards corpus. What is read out of a document is shown as *read*, never
 * as a judgement — the copy is careful about that throughout.
 */
export function EvidenceUpload({
  productId,
  onChange,
  onCountChange,
}: {
  productId: string
  /** Fired after a successful upload or delete, so a parent can re-run analysis. */
  onChange?: (count: number) => void
  /** Fired whenever the number of documents on file changes. */
  onCountChange?: (count: number) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<UploadedEvidence[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [justAdded, setJustAdded] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  // A file awaiting classification because its type could not be inferred.
  const [staged, setStaged] = useState<File | null>(null)
  const [stagedCategory, setStagedCategory] = useState<UploadCategory>('other')

  const refresh = useCallback(() => {
    setLoading(true)
    api
      .listEvidence(productId)
      .then((r) => setItems(r.evidence))
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(refresh, [refresh])

  useEffect(() => {
    onCountChange?.(items.length)
  }, [items.length, onCountChange])

  const doUpload = useCallback(
    async (file: File, category: UploadCategory) => {
      setError('')
      setUploading(true)
      setProgress(0)
      try {
        const created = await api.uploadEvidence(productId, file, category, '', setProgress)
        setItems((prev) => [...prev.filter((i) => i.id !== created.id), created])
        setJustAdded(created.id)
        setExpanded(created.id)
        window.setTimeout(() => setJustAdded(null), 2500)
        onChange?.(items.length + 1)
      } catch (e) {
        setError(apiError(e))
      } finally {
        setUploading(false)
        setProgress(0)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [productId, items.length, onChange],
  )

  const onSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return
    const file = files[0]
    const guess = inferCategory(file.name)
    if (guess.confident) {
      void doUpload(file, guess.category)
    } else {
      // Low confidence — ask the user how to classify before storing it.
      setStaged(file)
      setStagedCategory(guess.category)
    }
  }

  const confirmStaged = () => {
    if (!staged) return
    const file = staged
    setStaged(null)
    void doUpload(file, stagedCategory)
  }

  const remove = async (id: string) => {
    setError('')
    try {
      await api.deleteEvidence(productId, id)
      setItems((prev) => prev.filter((i) => i.id !== id))
      onChange?.(Math.max(0, items.length - 1))
    } catch (e) {
      setError(apiError(e))
    }
  }

  return (
    <div>
      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => !uploading && !staged && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !uploading && !staged) inputRef.current?.click()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (!uploading && !staged) onSelect(e.dataTransfer.files)
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors ${
          dragging
            ? 'border-brand-400 bg-brand-50'
            : 'border-ink-200 bg-ink-50/40 hover:border-brand-300 hover:bg-brand-50/40'
        } ${uploading || staged ? 'pointer-events-none opacity-70' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => onSelect(e.target.files)}
        />
        {uploading ? (
          <>
            <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
            <span className="text-sm font-medium text-ink-700">Uploading… {progress}%</span>
            <div className="mt-1 h-1.5 w-40 overflow-hidden rounded-full bg-ink-200">
              <div className="h-full bg-brand-500 transition-all" style={{ width: `${progress || 4}%` }} />
            </div>
          </>
        ) : (
          <>
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <UploadCloud className="h-5 w-5" />
            </span>
            <span className="text-sm font-medium text-ink-700">Drag &amp; drop or choose a file</span>
            <span className="text-xs text-ink-400">
              PDF, PNG, JPG or TXT — we detect the document type for you.
            </span>
          </>
        )}
      </div>

      {/* Classification prompt, shown only when the type could not be inferred */}
      {staged && (
        <div className="mt-3 rounded-xl border border-brand-200 bg-brand-50/60 p-3.5">
          <p className="text-sm font-semibold text-ink-800">How should we classify this document?</p>
          <p className="mt-0.5 truncate text-xs text-ink-500">{staged.name}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <select
              className="field h-9 w-56 py-1.5"
              value={stagedCategory}
              onChange={(e) => setStagedCategory(e.target.value as UploadCategory)}
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {UPLOAD_CATEGORY_LABELS[c]}
                </option>
              ))}
            </select>
            <button className="btn-primary btn-sm" onClick={confirmStaged}>
              Upload
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setStaged(null)}>
              Cancel
            </button>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-ink-400">
            The type decides which kind of requirement this document can support, so it is worth
            getting right.
          </p>
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
          {error}
        </p>
      )}

      {/* Uploaded list */}
      {loading ? (
        <p className="mt-4 text-sm text-ink-400">Loading uploaded evidence…</p>
      ) : items.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {items.map((item) => {
            const meta = statusMeta(item.extraction_status)
            const isOpen = expanded === item.id
            const fields = item.extracted_fields
            const hasFields =
              fields &&
              (fields.model ||
                fields.result ||
                fields.report_number ||
                fields.laboratory ||
                fields.issued_on ||
                (fields.test_names && fields.test_names.length > 0) ||
                (fields.numeric_results && fields.numeric_results.length > 0))
            return (
              <li
                key={item.id}
                className={`rounded-xl border transition-colors ${
                  justAdded === item.id ? 'border-emerald-300 bg-emerald-50/60' : 'border-ink-200 bg-white'
                }`}
              >
                <div className="flex items-start gap-2.5 px-3 py-2.5">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ink-100 text-ink-500">
                    <FileIcon item={item} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-ink-800">{item.name}</span>
                      {justAdded === item.id && (
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-400">
                      <span title="Detected document type">
                        {UPLOAD_CATEGORY_LABELS[item.upload_category] ?? item.upload_category}
                      </span>
                      <span aria-hidden>·</span>
                      <span>{formatBytes(item.size_bytes)}</span>
                      {item.created_at && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{formatDate(item.created_at)}</span>
                        </>
                      )}
                    </div>
                    <span className={`chip mt-1.5 ${meta.chip}`}>{meta.label}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {(hasFields || item.has_text) && (
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        onClick={() => setExpanded(isOpen ? null : item.id)}
                        aria-expanded={isOpen}
                        title="Show what was read from this document"
                      >
                        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-ghost btn-sm text-rose-600 hover:bg-rose-50"
                      onClick={() => remove(item.id)}
                      title="Remove this evidence"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div className="border-t border-ink-100 px-3 py-3">
                    <p className="mb-2 text-xs leading-relaxed text-ink-500">{item.note}</p>
                    {hasFields ? (
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                        {fields.model && <Field label="Model" value={fields.model} />}
                        {fields.report_number && <Field label="Report / cert. no." value={fields.report_number} />}
                        {fields.laboratory && <Field label="Laboratory" value={fields.laboratory} />}
                        {fields.issued_on && <Field label="Issued" value={fields.issued_on} />}
                        {fields.result && (
                          <Field label="Stated result" value={`${fields.result} (as written in the document)`} />
                        )}
                        {fields.test_names && fields.test_names.length > 0 && (
                          <div className="col-span-2">
                            <dt className="font-semibold text-ink-500">Tests mentioned</dt>
                            <dd className="mt-1 flex flex-wrap gap-1">
                              {fields.test_names.map((t) => (
                                <span key={t} className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-200">
                                  {t}
                                </span>
                              ))}
                            </dd>
                          </div>
                        )}
                        {fields.numeric_results && fields.numeric_results.length > 0 && (
                          <div className="col-span-2">
                            <dt className="font-semibold text-ink-500">Measurements read</dt>
                            <dd className="mt-1 flex flex-wrap gap-1.5">
                              {fields.numeric_results.map((m, i) => (
                                <span key={`${m.label}-${i}`} className="rounded-md bg-ink-100 px-1.5 py-0.5 text-ink-600">
                                  {m.label}: {m.value} {m.unit}
                                </span>
                              ))}
                            </dd>
                          </div>
                        )}
                      </dl>
                    ) : (
                      <p className="text-xs text-ink-400">No structured fields could be read from this document.</p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="mt-4 text-xs leading-relaxed text-ink-400">
          No documents uploaded yet. A test report or certificate can move a matching requirement
          from “test required” to “supported” below.
        </p>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold text-ink-500">{label}</dt>
      <dd className="text-ink-800">{value}</dd>
    </div>
  )
}
