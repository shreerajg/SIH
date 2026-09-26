import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Bot,
  Cpu,
  Loader2,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react'
import { api, apiError } from '@/lib/api'
import type { RAGResponse, StandardSummary } from '@/lib/types'
import { titleCase } from '@/lib/format'
import { EvidenceCitation, EvidenceDrawer, useEvidenceDrawer } from '@/components/EvidenceDrawer'
import { ErrorState, RegulatoryBadge } from '@/components/primitives'

interface Turn {
  question: string
  response: RAGResponse | null
  error?: string
}

const SUGGESTIONS = [
  'What temperature rise test is required for a storage water heater?',
  'What must be printed on the rating label?',
  'Is DEMO-STD-002 mandatory?',
  'What are the small parts requirements for toys?',
  'What tests apply to a pressure cooker safety valve?',
]

export function Assistant() {
  const [params] = useSearchParams()
  const drawer = useEvidenceDrawer()
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const [standards, setStandards] = useState<StandardSummary[]>([])
  const [scope, setScope] = useState<string>(params.get('standard') ?? '')
  const bottomRef = useRef<HTMLDivElement>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const productId = params.get('product') ?? undefined

  useEffect(() => {
    api.listStandards().then(setStandards).catch(() => undefined)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, loading])

  const ask = async (value?: string) => {
    const q = (value ?? question).trim()
    if (!q || loading) return
    setQuestion('')
    setLoading(true)
    setTurns((prev) => [...prev, { question: q, response: null }])
    try {
      const response = await api.ragQuery({
        question: q,
        standard_ids: scope ? [scope] : [],
        product_id: productId,
        conversation_id: conversationId,
      })
      // Threading the id back is what makes "why is that necessary?" resolve
      // against the previous answer instead of the whole corpus.
      if (response.conversation_id) setConversationId(response.conversation_id)
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, response } : t)),
      )
    } catch (e) {
      const message = apiError(e)
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: message } : t)),
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-4xl flex-col px-4 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 py-5">
        <div>
          <div className="section-title">Standards assistant</div>
          <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-ink-900">
            Ask, and see exactly where the answer came from
          </h1>
        </div>
        <div className="flex items-center gap-2">
        {turns.length > 0 && (
          <button
            className="btn-ghost btn-sm"
            onClick={() => {
              setTurns([])
              setConversationId(null)
            }}
            title="Start a fresh conversation with no carried context"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            New thread
          </button>
        )}
        <select
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm font-semibold text-ink-700"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
        >
          <option value="">Search all standards</option>
          {standards.map((s) => (
            <option key={s.id} value={s.id}>
              {s.display_number} — {s.title.slice(0, 46)}
            </option>
          ))}
        </select>
        </div>
      </header>

      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto pb-6">
        {turns.length === 0 && (
          <div className="card p-6">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <Bot className="h-4 w-4" />
              </span>
              <h2 className="text-sm font-bold text-ink-900">Grounded question answering</h2>
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-ink-600">
              Every answer is assembled from clauses retrieved out of the corpus, and each claim is
              checked against the evidence that was actually retrieved before it is shown. If the
              corpus cannot answer, the assistant says so instead of guessing.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="rounded-xl border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-600 hover:border-brand-300 hover:bg-brand-50"
                  onClick={() => void ask(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, index) => (
          <div key={index} className="space-y-3">
            <div className="flex justify-end">
              <div className="flex max-w-[85%] items-start gap-2.5 rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">
                <span>{turn.question}</span>
                <User className="mt-0.5 h-4 w-4 shrink-0 opacity-70" />
              </div>
            </div>

            {turn.error && <ErrorState message={turn.error} />}

            {!turn.response && !turn.error && (
              <div className="card flex items-center gap-2.5 p-4 text-sm text-ink-500">
                <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
                Retrieving relevant clauses and verifying evidence…
              </div>
            )}

            {turn.response && <AnswerCard response={turn.response} onOpenSource={drawer.open} />}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="sticky bottom-0 border-t border-ink-200 bg-ink-50 py-4"
        onSubmit={(e) => {
          e.preventDefault()
          void ask()
        }}
      >
        <div className="flex gap-2">
          <input
            className="field flex-1"
            placeholder="Ask about a requirement, a test, a clause or a regulatory status…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button className="btn-primary" type="submit" disabled={loading || !question.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Ask
          </button>
        </div>
      </form>

      <EvidenceDrawer chunkId={drawer.chunkId} onClose={drawer.close} onNavigate={drawer.open} />
    </div>
  )
}

function AnswerCard({
  response,
  onOpenSource,
}: {
  response: RAGResponse
  onOpenSource: (chunkId: string) => void
}) {
  const shield = response.evidence_shield
  return (
    <article className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-ink-200 bg-ink-50/70 px-4 py-2.5">
        <span className="chip bg-white text-ink-600 ring-1 ring-ink-200">
          {titleCase(response.query_type)}
        </span>
        <span
          className={`chip ${
            shield.verified
              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
              : 'bg-amber-50 text-amber-700 ring-1 ring-amber-200'
          }`}
          title={shield.reason}
        >
          {shield.verified ? (
            <ShieldCheck className="h-3.5 w-3.5" />
          ) : (
            <ShieldAlert className="h-3.5 w-3.5" />
          )}
          {shield.verified ? 'Evidence verified' : 'Insufficient evidence'}
        </span>
        <span className="chip bg-white text-ink-500 ring-1 ring-ink-200">
          {response.llm_used ? (
            <Sparkles className="h-3.5 w-3.5" />
          ) : (
            <Cpu className="h-3.5 w-3.5" />
          )}
          {response.llm_used ? 'AI + Retrieval, claim-checked' : 'Retrieval-only'}
        </span>
        {response.follow_up && (
          <span
            className="chip bg-violet-50 text-violet-700 ring-1 ring-violet-200"
            title={response.scope_note}
          >
            Follow-up
          </span>
        )}
        {response.regulatory && (
          <RegulatoryBadge
            status={response.regulatory.status}
            verified={response.regulatory.verified}
          />
        )}
      </div>

      <div className="px-4 py-4">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-800">{response.answer}</p>

        {response.claims.length > 0 && (
          <section className="mt-4">
            <div className="section-title mb-2">
              Verified claims ({shield.supported_claims} of {shield.total_claims})
            </div>
            <ul className="space-y-2">
              {response.claims.map((claim, i) => (
                <li key={i} className="rounded-xl border border-ink-200 bg-white px-3.5 py-2.5">
                  <p className="text-sm leading-relaxed text-ink-700">{claim.text}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {claim.source_chunk_ids.map((chunkId) => {
                      const citation = response.citations.find((c) => c.chunk_id === chunkId)
                      return citation ? (
                        <EvidenceCitation
                          key={chunkId}
                          citation={citation}
                          onOpen={onOpenSource}
                        />
                      ) : null
                    })}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {shield.rejected_claims.length > 0 && (
          <section className="mt-4 rounded-xl border border-rose-200 bg-rose-50/60 px-3.5 py-3">
            <div className="section-title mb-1.5 text-rose-700">
              Evidence Shield removed {shield.rejected_claims.length} claim(s)
            </div>
            <ul className="space-y-1.5">
              {shield.rejected_claims.map((rejected, i) => (
                <li key={i} className="text-xs leading-relaxed text-rose-800">
                  <span className="font-semibold">“{rejected.claim.slice(0, 120)}”</span> —{' '}
                  {rejected.reason}
                  {rejected.invalid_chunk_ids.length > 0 && (
                    <span className="font-mono"> ({rejected.invalid_chunk_ids.join(', ')})</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {response.citations.length > 0 && (
          <section className="mt-4 border-t border-ink-200 pt-3.5">
            <div className="section-title mb-2">
              Sources searched ({response.standards_searched.join(', ')})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {response.citations.map((citation) => (
                <EvidenceCitation
                  key={citation.chunk_id}
                  citation={citation}
                  onOpen={onOpenSource}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </article>
  )
}
