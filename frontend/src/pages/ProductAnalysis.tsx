import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, Cpu, Loader2, PackageSearch, Sparkles } from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { ProductProfile } from '@/lib/types'
import { attributeLabel, formatValue, titleCase } from '@/lib/format'
import { AIInterview } from '@/components/AIInterview'
import { ErrorState, LoadingSkeleton, SectionHeading } from '@/components/primitives'

export function ProductAnalysis() {
  const { productId = '' } = useParams()
  const navigate = useNavigate()
  const [product, setProduct] = useState<ProductProfile | null>(null)
  const [notes, setNotes] = useState<string[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [discovering, setDiscovering] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .getProduct(productId)
      .then(setProduct)
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(load, [load])

  const submitAnswers = async (answers: { field: string; value: unknown }[]) => {
    setBusy(true)
    try {
      const result = await api.answerInterview(productId, answers)
      setProduct(result.product)
      setNotes(result.notes)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setBusy(false)
    }
  }

  const skip = async (answers: { field: string; value: unknown }[]) => {
    setBusy(true)
    try {
      const result = await api.answerInterview(productId, answers, true)
      setProduct(result.product)
      setNotes(result.notes)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setBusy(false)
    }
  }

  const discover = async () => {
    setDiscovering(true)
    setError('')
    try {
      await api.discoverStandards(productId)
      navigate(`/product/${productId}/standards`)
    } catch (e) {
      setError(apiError(e))
      setDiscovering(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <LoadingSkeleton rows={2} />
      </div>
    )
  }

  if (error && !product) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <ErrorState message={error} onRetry={load} />
      </div>
    )
  }

  if (!product) return null

  const attributes = Object.entries(product.attributes).filter(
    ([, v]) => v !== null && v !== '' && v !== undefined,
  )

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <PackageSearch className="h-4.5 w-4.5" />
        </span>
        <span className="section-title">Step 1 of 4 · Product profile</span>
      </div>

      <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-ink-900">{product.name}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-500">{product.description}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {product.category ? (
          <span className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-200">
            {titleCase(product.category)}
          </span>
        ) : (
          <span className="chip bg-amber-50 text-amber-700 ring-1 ring-amber-200">
            Category not yet identified
          </span>
        )}
        <span
          className="chip bg-ink-100 text-ink-600"
          title="How this profile was produced"
        >
          {product.profile_source.includes('llm') ? (
            <Sparkles className="h-3.5 w-3.5" />
          ) : (
            <Cpu className="h-3.5 w-3.5" />
          )}
          {product.profile_source.includes('llm')
            ? 'Language model + deterministic extraction'
            : 'Deterministic extraction'}
        </span>
      </div>

      {notes.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {notes.map((note) => (
            <li key={note} className="rounded-lg bg-brand-50/70 px-3 py-2 text-sm text-brand-900">
              {note}
            </li>
          ))}
        </ul>
      )}

      <section className="mt-8">
        <SectionHeading
          title="Extracted attributes"
          description="Values read directly from your description, plus anything you have confirmed."
        />
        {attributes.length === 0 ? (
          <div className="card px-5 py-8 text-center text-sm text-ink-500">
            No attributes could be extracted yet. Answer the questions below.
          </div>
        ) : (
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {attributes.map(([key, value]) => (
              <div key={key} className="card px-4 py-3">
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                  {attributeLabel(key)}
                </dt>
                <dd className="mt-1 text-base font-bold text-ink-900">{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {product.missing_fields.length > 0 && (
        <section className="mt-8">
          <AIInterview
            questions={product.missing_fields}
            onSubmit={submitAnswers}
            onSkip={skip}
            busy={busy}
          />
        </section>
      )}

      {error && (
        <div className="mt-6">
          <ErrorState message={error} />
        </div>
      )}

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-ink-200 pt-6">
        <button className="btn-primary px-5 py-3 text-base" onClick={discover} disabled={discovering}>
          {discovering ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Discover applicable standards
          {!discovering && <ArrowRight className="h-4 w-4" />}
        </button>
        {product.missing_fields.length > 0 && (
          <p className="text-sm text-ink-500">
            You can search now — unanswered values will be reported as{' '}
            <span className="font-semibold">Unknown</span>, not assumed.
          </p>
        )}
      </div>

      {discovering && (
        <p className="mt-4 inline-flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Searching Indian Standards, ranking candidates and pulling scope evidence…
        </p>
      )}
    </div>
  )
}
