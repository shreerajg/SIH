import type { ReactNode } from 'react'
import {
  AlertTriangle,
  FlaskConical,
  Info,
  Loader2,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react'
import type { ComplianceStatus, Relevance, RegulatoryStatusValue } from '@/lib/types'
import { REGULATORY_META, RELEVANCE_META, STATUS_META } from '@/lib/format'

export function StatusBadge({ status, className = '' }: { status: ComplianceStatus; className?: string }) {
  const meta = STATUS_META[status]
  return (
    <span className={`chip ${meta.chip} ${className}`} title={meta.description}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}

export function RelevanceBadge({ relevance }: { relevance: Relevance }) {
  const meta = RELEVANCE_META[relevance]
  return (
    <span className={`chip ${meta.chip}`} title={meta.description}>
      {meta.label}
    </span>
  )
}

export function RegulatoryBadge({
  status,
  verified,
}: {
  status: RegulatoryStatusValue
  verified: boolean
}) {
  const meta = REGULATORY_META[status]
  // Regulatory status and source-type are separate concepts: a badge reading
  // "Mandatory DEMO" conflated a synthetic demo flag with a real regulatory
  // claim. Whether a record is synthetic is shown by the Demo Data badge; this
  // badge reports only the status, and says in its tooltip when that status is
  // itself synthetic.
  const synthetic = status !== 'UNABLE_TO_VERIFY' && !verified
  return (
    <span
      className={`chip ${meta.chip}`}
      title={
        synthetic
          ? `${meta.label} — this status belongs only to the synthetic demo corpus and is not an official regulatory claim.`
          : meta.label
      }
    >
      {status === 'UNABLE_TO_VERIFY' ? (
        <ShieldAlert className="h-3.5 w-3.5" />
      ) : (
        <ShieldCheck className="h-3.5 w-3.5" />
      )}
      {meta.label}
    </span>
  )
}

export function DemoDataBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className="chip bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200"
      title="This record comes from the labelled demonstration corpus, not an official BIS document."
    >
      <FlaskConical className="h-3.5 w-3.5" />
      {compact ? 'Demo' : 'Demo Dataset'}
    </span>
  )
}

export function DisclaimerBanner({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-xl border border-ink-200 bg-white/70 text-ink-600 ${
        compact ? 'px-3 py-2 text-xs' : 'px-4 py-3 text-sm'
      }`}
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" />
      <p className="leading-relaxed">{text}</p>
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-ink-100 text-ink-400">
        {icon ?? <Info className="h-5 w-5" />}
      </div>
      <div>
        <h3 className="text-base font-semibold text-ink-900">{title}</h3>
        <p className="mx-auto mt-1 max-w-md text-sm leading-relaxed text-ink-500">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="card border-rose-200 bg-rose-50/50 px-5 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-500" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-rose-900">Something went wrong</h3>
          <p className="mt-1 text-sm leading-relaxed text-rose-700">{message}</p>
          {onRetry && (
            <button className="btn-secondary btn-sm mt-3" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" />
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function LoadingSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card space-y-3 p-5">
          <div className="skeleton h-4 w-1/3" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-4/5" />
        </div>
      ))}
    </div>
  )
}

/**
 * Staged progress copy. The steps reflect what the backend is actually doing,
 * and advance on a timer only as a hint — the request drives completion.
 */
export function LoadingSteps({ steps, active }: { steps: string[]; active: number }) {
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2.5">
        <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
        <span className="text-sm font-semibold text-ink-900">{steps[Math.min(active, steps.length - 1)]}</span>
      </div>
      <ol className="mt-4 space-y-2">
        {steps.map((step, i) => (
          <li
            key={step}
            className={`flex items-center gap-2.5 text-sm ${
              i < active ? 'text-ink-400 line-through decoration-ink-300' : i === active ? 'text-ink-800' : 'text-ink-300'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                i < active ? 'bg-emerald-400' : i === active ? 'bg-brand-500' : 'bg-ink-200'
              }`}
            />
            {step}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function SectionHeading({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold tracking-tight text-ink-900">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-ink-500">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function Stat({
  label,
  value,
  tone = 'default',
  hint,
}: {
  label: string
  value: string | number
  tone?: 'default' | 'good' | 'warn' | 'bad' | 'muted' | 'brand'
  hint?: string
}) {
  const tones = {
    default: 'text-ink-900',
    good: 'text-emerald-600',
    warn: 'text-amber-600',
    bad: 'text-rose-600',
    muted: 'text-ink-400',
    brand: 'text-brand-600',
  }
  return (
    <div className="card px-4 py-3.5" title={hint}>
      <div className={`text-2xl font-bold tabular-nums tracking-tight ${tones[tone]}`}>{value}</div>
      <div className="mt-0.5 text-xs font-medium leading-tight text-ink-500">{label}</div>
    </div>
  )
}
