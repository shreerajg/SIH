import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Boxes,
  Camera,
  Loader2,
  MessageSquare,
  ScanText,
  Search,
  ShieldQuestion,
  Sparkles,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type {
  ConsumerCategory,
  ConsumerStandardResponse,
  OcrScanResponse,
  StandardSummary,
} from '@/lib/types'
import { DemoDataBadge, DisclaimerBanner, ErrorState, RegulatoryBadge } from '@/components/primitives'
import { EvidenceCitation, EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'

const EXAMPLES = ['DEMO-STD-001', 'DEMO-STD-004', 'DEMO-STD-005', 'DEMO-STD-007']

export function Consumer() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<ConsumerStandardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const drawer = useEvidenceDrawer()
  const navigate = useNavigate()

  // Browse-by-product-type: for a consumer who has no code to type at all.
  const [categories, setCategories] = useState<ConsumerCategory[]>([])
  const [activeCategory, setActiveCategory] = useState<ConsumerCategory | null>(null)
  const [categoryStandards, setCategoryStandards] = useState<StandardSummary[]>([])
  const [categoryLoading, setCategoryLoading] = useState(false)

  // Scan a photographed label instead of typing a code.
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [scanning, setScanning] = useState(false)
  const [scanInfo, setScanInfo] = useState<OcrScanResponse | null>(null)

  useEffect(() => {
    api
      .consumerCategories()
      .then((r) => setCategories(r.categories))
      .catch(() => undefined)
  }, [])

  const lookup = async (value?: string) => {
    const q = (value ?? query).trim()
    if (!q) return
    setQuery(q)
    setActiveCategory(null)
    setScanInfo(null)
    setLoading(true)
    setError('')
    try {
      setResult(await api.consumerLookup(q))
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }

  const scanLabel = async (file: File) => {
    setActiveCategory(null)
    setError('')
    setScanning(true)
    setScanInfo(null)
    setResult(null)
    try {
      const response = await api.consumerScan(file)
      setScanInfo(response)
      if (response.result) {
        setResult(response.result)
        setQuery(response.result.query)
      }
    } catch (e) {
      setError(apiError(e))
    } finally {
      setScanning(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const browseCategory = async (category: ConsumerCategory) => {
    setResult(null)
    setError('')
    setActiveCategory(category)
    setCategoryLoading(true)
    try {
      setCategoryStandards(await api.listStandards(category.key))
    } catch (e) {
      setError(apiError(e))
    } finally {
      setCategoryLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
          <ShieldQuestion className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Consumer mode</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900 sm:text-4xl">
        What does that code on the label mean?
      </h1>
      <p className="mt-3 max-w-2xl text-base leading-relaxed text-ink-600">
        Type the standard number printed on a product and get a plain-language explanation of what
        it covers — with the source text available if you want it.
      </p>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault()
          void lookup()
        }}
      >
        <label className="label" htmlFor="is-code">
          Enter an IS code, or just what the product is
        </label>
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-[240px] flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
            <input
              id="is-code"
              className="field pl-10 text-base"
              placeholder="e.g. DEMO-STD-001, IS 302, or 'pressure cooker'"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <button className="btn-primary px-5" type="submit" disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Look up
          </button>
          <button
            className="btn-secondary px-4"
            type="button"
            disabled={scanning}
            onClick={() => fileInputRef.current?.click()}
            title="Scan a photo of the standards mark on the product"
          >
            {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
            Scan a label
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg"
            capture="environment"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void scanLabel(file)
            }}
          />
        </div>
      </form>

      {scanInfo && (
        <div className="mt-4 card border-brand-200 bg-brand-50/40 p-4">
          <div className="flex items-center gap-2 text-sm font-bold text-ink-900">
            <ScanText className="h-4 w-4 text-brand-600" />
            What was read from your photo
          </div>
          {scanInfo.ocr_available ? (
            <>
              {scanInfo.raw_text ? (
                <p className="mt-2 rounded-lg bg-white px-3 py-2 font-mono text-xs leading-relaxed text-ink-600 ring-1 ring-ink-200">
                  {scanInfo.raw_text}
                </p>
              ) : null}
              {scanInfo.candidates.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {scanInfo.candidates.map((c) => (
                    <span key={c} className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                      {c}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs leading-relaxed text-ink-500">{scanInfo.note}</p>
            </>
          ) : (
            <p className="mt-2 text-xs leading-relaxed text-amber-700">{scanInfo.note}</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-ink-400">Try:</span>
        {EXAMPLES.map((code) => (
          <button
            key={code}
            className="rounded-lg border border-ink-200 bg-white px-2.5 py-1 font-mono text-xs font-semibold text-ink-600 hover:border-brand-300 hover:bg-brand-50"
            onClick={() => void lookup(code)}
          >
            {code}
          </button>
        ))}
      </div>

      {/* Browse by product type — for a consumer with no code to type at all. */}
      {!result && categories.length > 0 && (
        <div className="mt-8">
          {activeCategory ? (
            <div>
              <button
                className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold text-ink-500 hover:text-ink-800"
                onClick={() => setActiveCategory(null)}
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                All product types
              </button>
              <div className="section-title mb-2">{activeCategory.label}</div>
              {categoryLoading ? (
                <p className="text-sm text-ink-400">Loading standards…</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {categoryStandards.map((standard) => (
                    <button
                      key={standard.id}
                      onClick={() => void lookup(standard.is_number)}
                      className="card card-hover p-4 text-left"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-bold text-brand-700">
                          {standard.display_number}
                        </span>
                        {standard.is_mock && <DemoDataBadge compact />}
                      </div>
                      <p className="mt-1 text-sm font-semibold text-ink-800">{standard.title}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div>
              <div className="section-title mb-2">Or browse by what you own</div>
              <div className="flex flex-wrap gap-2">
                {categories.map((category) => (
                  <button
                    key={category.key}
                    onClick={() => void browseCategory(category)}
                    className="inline-flex items-center gap-2 rounded-xl border border-ink-200 bg-white px-3.5 py-2 text-sm font-semibold text-ink-700 transition-colors hover:border-brand-300 hover:bg-brand-50"
                  >
                    <Boxes className="h-3.5 w-3.5 text-ink-400" />
                    {category.label}
                    <span className="rounded-full bg-ink-100 px-1.5 py-0.5 text-[10px] font-bold text-ink-500">
                      {category.standard_count}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mt-6">
          <ErrorState message={error} onRetry={() => void lookup()} />
        </div>
      )}

      {result && !result.found && (
        <div className="mt-8 space-y-4">
          <div className="card border-amber-200 bg-amber-50/60 p-5">
            <h2 className="text-base font-bold text-amber-900">Not found in this corpus</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-amber-900/80">{result.message}</p>
          </div>
          {result.suggestions.length > 0 && (
            <div>
              <div className="section-title mb-2">Standards that are loaded</div>
              <div className="grid gap-2 sm:grid-cols-2">
                {result.suggestions.map((standard) => (
                  <button
                    key={standard.id}
                    onClick={() => void lookup(standard.is_number)}
                    className="card card-hover p-4 text-left"
                  >
                    <span className="font-mono text-xs font-bold text-brand-700">
                      {standard.display_number}
                    </span>
                    <p className="mt-1 text-sm font-semibold text-ink-800">{standard.title}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {result?.found && result.standard && (
        <article className="mt-8 space-y-5 animate-fade-up">
          <div className="card overflow-hidden">
            <div className="border-b border-ink-200 bg-gradient-to-r from-emerald-50 to-white px-6 py-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-lg bg-ink-900 px-2.5 py-1 font-mono text-sm font-bold text-white">
                  {result.standard.display_number}
                </span>
                {result.regulatory && (
                  <RegulatoryBadge
                    status={result.regulatory.status}
                    verified={result.regulatory.verified}
                  />
                )}
                {result.standard.is_mock && <DemoDataBadge />}
              </div>
              <h2 className="mt-3 text-xl font-bold leading-snug text-ink-900">
                {result.standard.title}
              </h2>
            </div>

            <div className="space-y-5 px-6 py-5">
              <section>
                <div className="section-title mb-1.5">What is this standard?</div>
                <p className="text-base leading-relaxed text-ink-700">{result.what_is_it}</p>
                {result.llm_used && (
                  <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-violet-600">
                    <Sparkles className="h-3 w-3" />
                    Simplified by a language model from the standard&apos;s own scope text
                  </p>
                )}
              </section>

              {result.what_it_covers.length > 0 && (
                <section>
                  <div className="section-title mb-2">What it covers</div>
                  <div className="flex flex-wrap gap-2">
                    {result.what_it_covers.map((area) => (
                      <span key={area} className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-200">
                        {area}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {result.applies_to && (
                <section>
                  <div className="section-title mb-1.5">What it applies to</div>
                  <p className="text-sm leading-relaxed text-ink-600">{result.applies_to}</p>
                </section>
              )}

              <section>
                <div className="section-title mb-1.5">Why it matters</div>
                <p className="text-sm leading-relaxed text-ink-600">{result.why_it_matters}</p>
              </section>

              {result.regulatory && (
                <section className="rounded-xl bg-ink-50 px-4 py-3.5">
                  <div className="section-title mb-1.5">Is it required by law?</div>
                  <p className="text-sm leading-relaxed text-ink-700">{result.regulatory.message}</p>
                  {result.regulatory.effective_date && (
                    <p className="mt-1.5 text-xs text-ink-500">
                      Effective from {result.regulatory.effective_date}
                      {result.regulatory.notification_number
                        ? ` · ${result.regulatory.notification_number}`
                        : ''}
                    </p>
                  )}
                </section>
              )}

              {result.sources.length > 0 && (
                <section>
                  <div className="section-title mb-2">Where this came from</div>
                  <div className="flex flex-wrap gap-1.5">
                    {result.sources.map((source) => (
                      <EvidenceCitation
                        key={source.chunk_id}
                        citation={source}
                        onOpen={drawer.open}
                      />
                    ))}
                  </div>
                </section>
              )}

              <div className="flex flex-wrap gap-2 border-t border-ink-200 pt-4">
                <button
                  className="btn-primary btn-sm"
                  onClick={() =>
                    navigate(`/assistant?standard=${result.standard?.id ?? ''}`)
                  }
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  Ask a question about this standard
                </button>
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => navigate(`/standards/${result.standard?.id ?? ''}`)}
                >
                  See the full standard
                </button>
              </div>
            </div>
          </div>

          <DisclaimerBanner text={result.disclaimer} compact />
        </article>
      )}

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
    </div>
  )
}
