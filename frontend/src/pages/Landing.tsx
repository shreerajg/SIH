import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Boxes,
  FileSearch,
  GitCompareArrows,
  Quote,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'
import { useOutletContext } from 'react-router-dom'
import type { HealthResponse } from '@/lib/types'

const FEATURES = [
  {
    icon: ScanSearch,
    title: 'Discover applicable standards',
    body: 'Describe a product in plain English. The engine builds a structured profile and searches the standards corpus, prioritizing verified official sources. It never names a standard that was not retrieved.',
  },
  {
    icon: Quote,
    title: 'Clause-level evidence',
    body: 'Every answer resolves to a specific retrieved source passage, with the document type, clause/page reference and source text one click away.',
  },
  {
    icon: FileSearch,
    title: 'Pre-compliance gap analysis',
    body: 'Requirements are compared against declared values and evidence using a rule engine that assigns controlled outcomes such as supported, test-required, document-required and unknown — never a free-form LLM verdict.',
  },
  {
    icon: Boxes,
    title: 'Product Compliance Twin',
    body: 'One dashboard holding the product profile, standards, requirements, testing plan, evidence, gaps, regulatory status, amendments, graph and sources.',
  },
  {
    icon: GitCompareArrows,
    title: 'Amendment impact',
    body: 'Old and new source wording is compared deterministically, with numeric limit changes detected and their possible relevance to the product highlighted.',
  },
  {
    icon: Users,
    title: 'Consumer IS explanation',
    body: 'Type or scan a code from a product label and get a plain-language explanation grounded in the retrieved source, including what it covers, regulatory information and source evidence.',
  },
]

export function Landing() {
  const { health } = useOutletContext<{ health: HealthResponse | null }>()

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-ink-200 bg-white">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.55]"
          style={{
            backgroundImage:
              'radial-gradient(60rem 30rem at 15% -10%, #dae6ff 0%, transparent 60%), radial-gradient(45rem 25rem at 95% 0%, #ffefd4 0%, transparent 55%)',
          }}
        />
        <div className="relative mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-24">
          <div className="max-w-3xl">
            <span className="chip bg-white text-brand-700 ring-1 ring-brand-200">
              <Sparkles className="h-3.5 w-3.5" />
              Smart India Hackathon · SIH26107
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight text-ink-900 sm:text-5xl lg:text-6xl">
              Understand Indian Standards.
              <span className="block text-brand-700">
                Before they become your compliance problem.
              </span>
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-600">
              AI-powered standards discovery, evidence-backed pre-compliance intelligence, and
              simple BIS explanations — grounded in retrieved clause text, never in what a model
              remembers.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/manufacturer" className="btn-primary px-5 py-3 text-base">
                I&apos;m a Manufacturer
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/consumer" className="btn-secondary px-5 py-3 text-base">
                I&apos;m a Consumer
              </Link>
            </div>

            {health && (
              <dl className="mt-10 grid max-w-2xl grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
                <Metric value={health.corpus.standards} label="Standards indexed" />
                <Metric value={health.corpus.clauses} label="Clause chunks" />
                <Metric value={health.corpus.requirements} label="Structured requirements" />
                <Metric value={health.corpus.regulatory_records} label="Regulatory records" />
              </dl>
            )}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <div className="max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
            Not a chatbot over PDFs
          </h2>
          <p className="mt-2 text-base leading-relaxed text-ink-600">
            The chat window is one interface. Underneath it is a retrieval engine, a rule-based
            compliance analyzer, and a validation layer that can reject the model&apos;s own output.
          </p>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="card card-hover p-5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <feature.icon className="h-4.5 w-4.5" />
              </div>
              <h3 className="mt-3.5 text-base font-bold text-ink-900">{feature.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Trust strip */}
      <section className="border-y border-ink-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-[1fr_1.2fr]">
            <div>
              <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                <ShieldCheck className="h-3.5 w-3.5" />
                Anti-hallucination by construction
              </span>
              <h2 className="mt-4 text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
                The model is not allowed to be the source of truth
              </h2>
              <p className="mt-3 text-base leading-relaxed text-ink-600">
                Standard identifiers, regulatory status and compliance statuses all come from
                structured records. The retrieval engine finds and ranks the evidence. When an LLM
                is enabled, it only explains information that was retrieved — the backend validates
                generated claims before they are displayed.
              </p>
              <Link to="/trust" className="btn-secondary mt-5">
                How it works
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>

            <ul className="space-y-3">
              {[
                ['Closed candidate list', 'A standard ID the model returns that was not retrieved is discarded before it can be displayed.'],
                ['Evidence Shield', 'Each claim must cite a chunk that was in the retrieved context. Claims that cite anything else are removed.'],
                ['Structured regulatory status', 'Mandatory, upcoming, withdrawn, voluntary, or unable-to-verify status comes only from structured QCO/regulatory records — never from model guessing.'],
                ['Closed status vocabulary', 'Gap statuses are produced by a rule engine from a fixed enumeration, so the assessment is reproducible.'],
              ].map(([title, body]) => (
                <li key={title} className="card flex gap-3.5 p-4">
                  <ShieldCheck className="mt-0.5 h-4.5 w-4.5 shrink-0 text-emerald-500" />
                  <div>
                    <h3 className="text-sm font-bold text-ink-900">{title}</h3>
                    <p className="mt-0.5 text-sm leading-relaxed text-ink-600">{body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  )
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <dd className="text-2xl font-extrabold tabular-nums tracking-tight text-ink-900">{value}</dd>
      <dt className="mt-0.5 text-xs font-medium text-ink-500">{label}</dt>
    </div>
  )
}
