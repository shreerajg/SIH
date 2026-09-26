import { useCallback, useEffect, useState } from 'react'
import {
  BadgeCheck,
  Building2,
  ExternalLink,
  Factory,
  Gem,
  Info,
  MapPin,
  ShieldAlert,
  Users,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type {
  AssayingCentre,
  ConsumerHallmarkGuide,
  HuidDescription,
  JewellerHallmarkGuide,
  VerificationState,
} from '@/lib/types'
import { EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { ErrorState, LoadingSkeleton, SectionHeading } from '@/components/primitives'

/**
 * BIS hallmarking guidance — consumer and jeweller.
 *
 * Everything shown here was resolved to a clause in an official BIS hallmarking
 * document before it reached the page; the small "Source" buttons open that
 * clause in the same evidence drawer the rest of the platform uses.
 *
 * The HUID box is deliberately not a validator. It describes a code against the
 * documented format and always says the code was not checked against BIS,
 * because no HUID verification service is integrated.
 */

const STATE_CHIP: Record<VerificationState, string> = {
  VERIFIED: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  PARTIALLY_VERIFIED: 'bg-saffron-50 text-saffron-800 ring-1 ring-saffron-200',
  UNABLE_TO_VERIFY: 'bg-ink-100 text-ink-700 ring-1 ring-ink-200',
}

const ACTOR_META: Record<string, { label: string; icon: typeof Factory }> = {
  jeweller: { label: 'Jeweller', icon: Factory },
  ahc: { label: 'A&H Centre', icon: Building2 },
  bis: { label: 'BIS', icon: Building2 },
  both: { label: 'Jeweller and BIS', icon: Users },
}

function SourceButton({
  chunkId,
  label,
  onOpen,
}: {
  chunkId: string | undefined
  label?: string
  onOpen: (id: string) => void
}) {
  if (!chunkId) return null
  return (
    <button
      type="button"
      onClick={() => onOpen(chunkId)}
      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-saffron-700 hover:underline"
    >
      <BadgeCheck className="h-3 w-3" />
      {label ?? 'Source'}
    </button>
  )
}

function Unverified({ note }: { note: string }) {
  return (
    <p className="mt-1 rounded bg-ink-50 p-2 text-xs leading-relaxed text-ink-600">
      <Info className="mr-1 inline h-3 w-3" />
      {note || 'Unable to verify this point from the available BIS data.'}
    </p>
  )
}

// ---------------------------------------------------------------------------

function HuidBox({ huid }: { huid: ConsumerHallmarkGuide['huid'] }) {
  const [code, setCode] = useState('')
  const [result, setResult] = useState<HuidDescription | null>(null)
  const [busy, setBusy] = useState(false)

  const describe = async () => {
    if (!code.trim()) return
    setBusy(true)
    try {
      setResult(await api.describeHuid(code.trim()))
    } catch {
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card p-5">
      <h3 className="text-base font-semibold text-ink-900">HUID</h3>
      {huid?.description && (
        <p className="mt-2 text-sm leading-relaxed text-ink-600">{huid.description}</p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Enter a HUID to check its format"
          className="min-w-[14rem] flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm"
          aria-label="HUID"
        />
        <button type="button" className="btn-secondary" onClick={describe} disabled={busy}>
          {busy ? 'Checking format…' : 'Check format'}
        </button>
      </div>

      {result && (
        <div className="mt-3 rounded-lg bg-ink-50 p-3">
          <ul className="space-y-1 text-sm text-ink-700">
            {result.observations.map((o, i) => (
              <li key={i}>• {o}</li>
            ))}
          </ul>
          {/* The load-bearing statement: nothing was verified. */}
          <p className="mt-2 flex items-start gap-1.5 rounded bg-saffron-50 p-2 text-xs leading-relaxed text-saffron-900 ring-1 ring-saffron-200">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              <strong>Not verified.</strong> {result.verification_note}
            </span>
          </p>
        </div>
      )}

      <p className="mt-3 text-xs leading-relaxed text-ink-500">{huid?.verification_note}</p>
      {huid?.official_verification_url && (
        <a
          href={huid.official_verification_url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-saffron-700 hover:underline"
        >
          Official BIS hallmarking pages <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  )
}

function CentreFinder({ guide }: { guide: JewellerHallmarkGuide }) {
  const [state, setState] = useState('')
  const [results, setResults] = useState<AssayingCentre[]>([])
  const [total, setTotal] = useState(0)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const summary = guide.centre_summary

  const search = async (nextState: string) => {
    setState(nextState)
    if (!nextState) {
      setResults([])
      setTotal(0)
      setMessage('')
      return
    }
    setBusy(true)
    try {
      const r = await api.hallmarkingCentres({ state: nextState, operative_only: true })
      setResults(r.results)
      setTotal(r.total_matching)
      setMessage(r.message)
    } finally {
      setBusy(false)
    }
  }

  if (!summary.available) {
    return (
      <div className="card p-5">
        <p className="text-sm leading-relaxed text-ink-600">{summary.note}</p>
      </div>
    )
  }

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-ink-900">
          Assaying &amp; Hallmarking Centres
        </h3>
        <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
          {summary.operative} operative of {summary.total}
        </span>
      </div>

      <select
        value={state}
        onChange={(e) => search(e.target.value)}
        className="mt-3 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
        aria-label="State"
      >
        <option value="">Choose a state…</option>
        {summary.states.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {busy && <p className="mt-3 text-sm text-ink-500">Searching…</p>}

      {!busy && results.length > 0 && (
        <>
          <p className="mt-3 text-xs text-ink-500">
            Showing {results.length} of {total} operative centres in {state}.
          </p>
          <ul className="mt-2 max-h-80 space-y-2 overflow-y-auto">
            {results.map((c) => (
              <li key={c.recognition_number} className="rounded-lg bg-ink-50/70 p-3">
                <p className="text-sm font-medium text-ink-900">{c.name}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-600">
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-3 w-3" />
                    {c.city}
                    {c.state ? `, ${c.state}` : ''}
                  </span>
                  <span>·</span>
                  <span>{c.recognition_number}</span>
                  {c.scope && (
                    <>
                      <span>·</span>
                      <span>{c.scope}</span>
                    </>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}

      {!busy && state && results.length === 0 && message && (
        <p className="mt-3 text-sm leading-relaxed text-ink-600">{message}</p>
      )}

      <p className="mt-3 text-xs leading-relaxed text-ink-500">{summary.note}</p>
      {summary.source_url && (
        <a
          href={summary.source_url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-saffron-700 hover:underline"
        >
          Live BIS centre list <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

export function Hallmarking() {
  const [tab, setTab] = useState<'consumer' | 'jeweller'>('consumer')
  const [consumer, setConsumer] = useState<ConsumerHallmarkGuide | null>(null)
  const [jeweller, setJeweller] = useState<JewellerHallmarkGuide | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const drawer = useEvidenceDrawer()

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([api.hallmarkingConsumerGuide('gold'), api.hallmarkingJewellerGuide()])
      .then(([c, j]) => {
        setConsumer(c)
        setJeweller(j)
      })
      .catch((e) => setError(apiError(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  if (loading) return <LoadingSkeleton />
  if (error) return <ErrorState message={error} onRetry={load} />

  const overview = consumer?.overview

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-wide text-saffron-700">
        BIS hallmarking
      </p>
      <h1 className="mt-1 flex items-center gap-2 text-3xl font-bold tracking-tight text-ink-900">
        <Gem className="h-7 w-7 text-saffron-600" />
        Hallmarking guidance
      </h1>

      {overview?.summary && (
        <div className="mt-3 max-w-3xl">
          <p className="text-base leading-relaxed text-ink-600">{overview.summary}</p>
          <SourceButton chunkId={overview.evidence?.chunk_id} onOpen={drawer.open} />
        </div>
      )}

      {consumer && (
        <p className="mt-3 text-xs text-ink-500">{consumer.message}</p>
      )}

      {/* --- tabs ------------------------------------------------------- */}
      <div className="mt-6 flex gap-1 border-b border-ink-200">
        {(
          [
            ['consumer', 'For consumers'],
            ['jeweller', 'For jewellers'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`px-4 py-2 text-sm font-medium transition ${
              tab === id
                ? 'border-b-2 border-saffron-600 text-ink-900'
                : 'text-ink-500 hover:text-ink-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* --- consumer --------------------------------------------------- */}
      {tab === 'consumer' && consumer && (
        <div className="mt-6 space-y-8">
          <section>
            <SectionHeading
              title="What a hallmarked gold article carries"
              description="The marks BIS requires, each shown with the clause that states it."
            />
            <div className="grid gap-3 sm:grid-cols-3">
              {consumer.components.map((c) => (
                <div key={c.id} className="card p-4">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-ink-900">{c.name}</h3>
                    <span className={`chip ${STATE_CHIP[c.state]}`}>{c.state}</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-ink-600">{c.description}</p>
                  <SourceButton chunkId={c.evidence?.chunk_id} onOpen={drawer.open} />
                </div>
              ))}
            </div>
          </section>

          <section>
            <SectionHeading
              title="Permitted purity grades"
              description="Read from stored records transcribed from BIS documents — no grade is inferred."
            />
            <div className="card overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 text-left text-xs uppercase tracking-wide text-ink-500">
                  <tr>
                    <th className="px-4 py-2">Carat</th>
                    <th className="px-4 py-2">Fineness</th>
                    <th className="px-4 py-2">Marking</th>
                    <th className="px-4 py-2">Mandatory order</th>
                    <th className="px-4 py-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {consumer.purity_grades.map((g) => (
                    <tr key={g.id} className="border-t border-ink-100">
                      <td className="px-4 py-2 font-medium text-ink-900">{g.carat ?? '—'}</td>
                      <td className="px-4 py-2 text-ink-700">{g.fineness ?? '—'}</td>
                      <td className="px-4 py-2 text-ink-700">{g.permitted_marking ?? '—'}</td>
                      <td className="px-4 py-2 text-ink-700">
                        {g.mandatory_order_covered ? 'Covered' : g.note ? 'See note' : '—'}
                      </td>
                      <td className="px-4 py-2">
                        <SourceButton chunkId={g.evidence?.chunk_id} onOpen={drawer.open} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <SectionHeading title="What to check before you buy" />
            <ol className="space-y-3">
              {consumer.checks.map((c, i) => (
                <li key={c.id} className="card p-4">
                  <p className="text-sm leading-relaxed text-ink-800">
                    <span className="mr-2 font-semibold text-saffron-700">{i + 1}.</span>
                    {c.text}
                  </p>
                  {c.evidence ? (
                    <SourceButton chunkId={c.evidence.chunk_id} onOpen={drawer.open} />
                  ) : (
                    <Unverified note={c.note} />
                  )}
                </li>
              ))}
            </ol>
          </section>

          <section>
            <SectionHeading title="HUID" />
            <HuidBox huid={consumer.huid} />
          </section>
        </div>
      )}

      {/* --- jeweller --------------------------------------------------- */}
      {tab === 'jeweller' && jeweller && (
        <div className="mt-6 space-y-8">
          <section>
            <SectionHeading
              title={jeweller.title}
              description={jeweller.summary}
              action={
                <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                  {jeweller.stages_with_evidence} of {jeweller.stages.length} steps cited
                </span>
              }
            />
            <ol className="space-y-4 border-l border-ink-200 pl-3">
              {jeweller.stages.map((s) => {
                const meta = ACTOR_META[s.actor] ?? ACTOR_META.jeweller
                const ActorIcon = meta.icon
                return (
                  <li key={s.id} className="relative pl-10">
                    <span className="absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full bg-saffron-600 text-xs font-semibold text-white">
                      {s.order}
                    </span>
                    <div className="card p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <h3 className="text-sm font-semibold text-ink-900">{s.title}</h3>
                        <span className="chip bg-ink-100 text-ink-700 ring-1 ring-ink-200">
                          <ActorIcon className="h-3.5 w-3.5" />
                          {meta.label}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-ink-600">{s.summary}</p>
                      {s.what_you_do.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {s.what_you_do.map((w, i) => (
                            <li key={i} className="flex gap-2 text-sm text-ink-700">
                              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" />
                              {w}
                            </li>
                          ))}
                        </ul>
                      )}
                      {s.evidence ? (
                        <SourceButton
                          chunkId={s.evidence.chunk_id}
                          label={`Source · ${s.evidence.standard_id} clause ${s.evidence.clause_number}`}
                          onOpen={drawer.open}
                        />
                      ) : (
                        <Unverified note={s.evidence_note} />
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
          </section>

          <section>
            <SectionHeading
              title="Where to get articles hallmarked"
              description="A snapshot of the directory BIS publishes. Confirm against the live list before relying on it."
            />
            <CentreFinder guide={jeweller} />
          </section>
        </div>
      )}

      <p className="mt-10 text-xs leading-relaxed text-ink-500">
        Every point above is resolved to a clause in an official BIS hallmarking document before it
        is shown; anything that could not be is marked “unable to verify” rather than stated. This
        platform does not verify HUIDs, jeweller registrations or centre recognition — it reports
        what the BIS documents it holds say.
      </p>

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
    </div>
  )
}
