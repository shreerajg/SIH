import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  ExternalLink,
  FileText,
  Factory,
  Info,
  Users,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { ProcessGuidance, ProcessStage } from '@/lib/types'
import { EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeading } from '@/components/primitives'

/**
 * "How do I actually get certified?" — the Scheme-I journey, step by step.
 *
 * Every step that can be is backed by a clause from this product's own BIS
 * documents, opened in the same evidence drawer used everywhere else. Steps
 * with no supporting clause are still listed but say so plainly, and the BIS
 * application stage is marked as not held in this corpus rather than being
 * described from memory.
 */

const ACTOR_META: Record<string, { label: string; icon: typeof Factory; chip: string }> = {
  manufacturer: {
    label: 'You (manufacturer)',
    icon: Factory,
    chip: 'bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200',
  },
  bis: {
    label: 'BIS',
    icon: Building2,
    chip: 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200',
  },
  both: {
    label: 'You and BIS',
    icon: Users,
    chip: 'bg-ink-100 text-ink-700 ring-1 ring-ink-200',
  },
}

function Stage({
  stage,
  onViewSource,
}: {
  stage: ProcessStage
  onViewSource: (chunkId: string) => void
}) {
  const meta = ACTOR_META[stage.actor] ?? ACTOR_META.manufacturer
  const ActorIcon = meta.icon

  return (
    <li className="relative pl-10">
      {/* timeline rail */}
      <span className="absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full bg-saffron-600 text-xs font-semibold text-white">
        {stage.order}
      </span>

      <div className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="text-base font-semibold text-ink-900">{stage.title}</h3>
          <span className={`chip ${meta.chip}`}>
            <ActorIcon className="h-3.5 w-3.5" />
            {meta.label}
          </span>
        </div>

        <p className="mt-2 text-sm leading-relaxed text-ink-600">{stage.summary}</p>

        {stage.what_you_do.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {stage.what_you_do.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink-700">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" />
                {item}
              </li>
            ))}
          </ul>
        )}

        {stage.documents.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {stage.documents.map((doc) => (
              <span key={doc} className="chip bg-ink-50 text-ink-700 ring-1 ring-ink-200">
                <FileText className="h-3.5 w-3.5" />
                {doc}
              </span>
            ))}
          </div>
        )}

        {/* --- the citation, or an honest absence ------------------------ */}
        {stage.evidence ? (
          <button
            type="button"
            onClick={() => onViewSource(stage.evidence!.chunk_id)}
            className="mt-3 w-full rounded-lg bg-emerald-50/70 p-3 text-left ring-1 ring-emerald-100 transition hover:bg-emerald-50"
          >
            <span className="text-xs font-medium uppercase tracking-wide text-emerald-700">
              Source · {stage.evidence.display_number} clause {stage.evidence.clause_number}
              {stage.evidence.page_number ? ` · page ${stage.evidence.page_number}` : ''}
            </span>
            <span className="mt-1 block text-sm leading-relaxed text-ink-700">
              “{stage.evidence.excerpt}”
            </span>
          </button>
        ) : (
          <p className="mt-3 rounded-lg bg-ink-50 p-3 text-xs leading-relaxed text-ink-600">
            <Info className="mr-1 inline h-3.5 w-3.5" />
            {stage.evidence_note}
            {stage.external && stage.external_url && (
              <a
                href={stage.external_url}
                target="_blank"
                rel="noreferrer"
                className="ml-1 inline-flex items-center gap-1 font-medium text-saffron-700 hover:underline"
              >
                Official BIS page <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </p>
        )}
      </div>
    </li>
  )
}

export function CertificationProcess() {
  const { productId = '' } = useParams()
  const [guidance, setGuidance] = useState<ProcessGuidance | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const drawer = useEvidenceDrawer()

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .processForProduct(productId)
      .then(setGuidance)
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(load, [load])

  if (loading) return <LoadingSkeleton />
  if (error) return <ErrorState message={error} onRetry={load} />

  if (!guidance?.available) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <Link
          to={`/product/${productId}/standards`}
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-ink-600 hover:text-ink-900"
        >
          <ArrowLeft className="h-4 w-4" /> Back to standards
        </Link>
        <EmptyState
          title="No certification process can be shown"
          description={
            guidance?.message ??
            'No certification scheme has been confirmed for this product, so there is no process to describe.'
          }
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <Link
        to={`/product/${productId}/standards`}
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-ink-600 hover:text-ink-900"
      >
        <ArrowLeft className="h-4 w-4" /> Back to standards
      </Link>

      <p className="text-xs font-semibold uppercase tracking-wide text-saffron-700">
        Certification process guidance
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-ink-900">{guidance.title}</h1>
      <p className="mt-3 max-w-2xl text-base leading-relaxed text-ink-600">{guidance.summary}</p>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
          {guidance.stages_with_evidence} of {guidance.stages.length} steps clause-cited
        </span>
        {guidance.process_url && (
          <a
            href={guidance.process_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-medium text-saffron-700 hover:underline"
          >
            Official BIS certification process <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>

      {/* --- implementation timeline ------------------------------------- */}
      {guidance.timeline.available && (
        <section className="mt-8">
          <SectionHeading
            title="When you must comply"
            description="BIS sets different implementation dates by enterprise size — read from the order's own table."
          />
          <div className="card p-5">
            <div className="grid gap-3 sm:grid-cols-3">
              {guidance.timeline.deadlines.map((deadline, i) => (
                <div key={i} className="rounded-lg bg-ink-50/70 p-3">
                  <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-500">
                    <CalendarClock className="h-3.5 w-3.5" />
                    {deadline.enterprise_category}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-ink-900">{deadline.date}</p>
                  {deadline.standard && (
                    <p className="mt-0.5 text-xs text-ink-500">{deadline.standard}</p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-ink-500">{guidance.timeline.note}</p>
            {guidance.timeline.evidence && (
              <button
                type="button"
                onClick={() => drawer.open(guidance.timeline.evidence!.chunk_id)}
                className="mt-2 text-xs font-medium text-saffron-700 hover:underline"
              >
                View the source table
              </button>
            )}
          </div>
        </section>
      )}

      {/* --- the journey -------------------------------------------------- */}
      <section className="mt-8">
        <SectionHeading
          title="The journey"
          description="Each step is backed by a clause from the documents held for this product wherever one exists."
        />
        <ol className="space-y-4 border-l border-ink-200 pl-3">
          {guidance.stages.map((stage) => (
            <Stage key={stage.id} stage={stage} onViewSource={drawer.open} />
          ))}
        </ol>
      </section>

      <p className="mt-8 text-xs leading-relaxed text-ink-500">
        {guidance.message} This is preparation guidance drawn from the documents in this corpus,
        not an official BIS determination, and it does not replace the procedure BIS publishes.
      </p>

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
    </div>
  )
}
