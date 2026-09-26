import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Factory, Loader2 } from 'lucide-react'
import { api, apiError } from '@/lib/api'
import { ErrorState, LoadingSteps } from '@/components/primitives'

const SAMPLES = [
  {
    label: 'Water heater',
    text: 'We manufacture a 15 litre domestic electric storage water heater operating at 230 V with a 2000 W heating element and a vitreous enamel coated inner container.',
  },
  {
    label: 'Pressure cooker',
    text: 'We make 5 litre aluminium domestic pressure cookers with a vent weight, rated at 100 kPa operating pressure.',
  },
  {
    label: 'Helmet',
    text: 'We manufacture full face ABS shell helmets for two wheeler riders, mass 1.4 kg, with a clear visor.',
  },
  {
    label: 'Toy',
    text: 'We produce plastic rattles and painted wooden blocks for children under 18 months, sold in printed cartons.',
  },
  {
    label: 'Vague description',
    text: 'We manufacture heaters.',
  },
]

const STEPS = [
  'Understanding your product…',
  'Extracting structured attributes…',
  'Checking for missing information…',
]

//: The manufacturer workflow shown on the right. Order matches the actual
//: pipeline: profile -> discovery -> clause retrieval -> gap analysis -> twin.
const WORKFLOW = [
  { title: 'Describe product', line: 'Plain-English manufacturer input' },
  { title: 'Build product profile', line: 'Extract structured attributes' },
  { title: 'Discover standards', line: 'Hybrid semantic + keyword retrieval' },
  { title: 'Retrieve evidence', line: 'Relevant clauses and regulatory sources' },
  { title: 'Analyse gaps', line: 'Tests, documents and unknowns' },
  { title: 'Compliance Twin', line: 'Persistent product standards profile' },
]

export function Manufacturer() {
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading) return
    setStep(0)
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 900)
    return () => clearInterval(timer)
  }, [loading])

  const submit = async () => {
    if (description.trim().length < 5) {
      setError('Describe the product in a sentence or two so the profile has something to work from.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await api.analyzeProduct(description.trim())
      navigate(`/product-analysis/${result.product.id}`)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:py-16">
      <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-14">
        {/* LEFT — the input experience */}
        <div>
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <Factory className="h-4.5 w-4.5" />
            </span>
            <span className="section-title">Manufacturer / MSME</span>
          </div>

          <h1 className="mt-5 text-3xl font-extrabold leading-[1.12] tracking-tight text-ink-900 sm:text-4xl">
            Describe your product.
            <br className="hidden sm:block" /> We&apos;ll find the standards that matter.
          </h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-600">
            No IS code required. Tell us what you manufacture in plain English and include details
            such as capacity, voltage, material, intended use, or other important specifications.
          </p>

          <div className="mt-8">
            <label className="label" htmlFor="description">
              Product description
            </label>
            <textarea
              id="description"
              className="field min-h-[176px] resize-y text-base leading-relaxed"
              placeholder="We manufacture a 15 L domestic electric storage water heater operating at 230 V…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
            />
            <div className="mt-1.5 flex items-center justify-between text-xs text-ink-400">
              <span>Include capacity, voltage, materials and intended use where possible.</span>
              <span className="tabular-nums">{description.length} / 4000</span>
            </div>
          </div>

          <div className="mt-5">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">
              Try an example
            </div>
            <div className="flex flex-wrap gap-2">
              {SAMPLES.map((sample) => (
                <button
                  key={sample.label}
                  className="rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-semibold text-ink-600 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 disabled:opacity-50"
                  onClick={() => setDescription(sample.text)}
                  disabled={loading}
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-7 flex flex-wrap items-center gap-3">
            <button className="btn-primary px-6 py-3 text-base" onClick={submit} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Analyse product
              {!loading && <ArrowRight className="h-4 w-4" />}
            </button>
            <span className="text-sm text-ink-400">
              Nothing is saved beyond this browser session.
            </span>
          </div>

          {loading && (
            <div className="mt-6">
              <LoadingSteps steps={STEPS} active={step} />
            </div>
          )}

          {error && (
            <div className="mt-6">
              <ErrorState message={error} onRetry={submit} />
            </div>
          )}
        </div>

        {/* RIGHT — how the workflow runs */}
        <aside className="lg:pt-1">
          <div className="card p-6">
            <div className="section-title mb-5">How it works</div>
            <ol className="relative">
              {WORKFLOW.map((item, i) => (
                <li key={item.title} className="relative flex gap-3.5 pb-5 last:pb-0">
                  {i < WORKFLOW.length - 1 && (
                    <span
                      className="absolute left-[13.5px] top-7 bottom-0 w-px bg-ink-200"
                      aria-hidden
                    />
                  )}
                  <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700 ring-1 ring-brand-200 tabular-nums">
                    {i + 1}
                  </span>
                  <div className="pt-0.5">
                    <div className="text-sm font-bold leading-tight text-ink-900">{item.title}</div>
                    <div className="mt-0.5 text-xs leading-snug text-ink-500">{item.line}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </div>
    </div>
  )
}
