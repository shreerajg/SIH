import { useState } from 'react'
import { ArrowRight, MessageCircleQuestion, SkipForward } from 'lucide-react'
import type { MissingField } from '@/lib/types'

/**
 * Targeted follow-up questions. The platform asks rather than guesses when the
 * description is too thin to scope a search.
 */
export function AIInterview({
  questions,
  onSubmit,
  onSkip,
  busy,
}: {
  questions: MissingField[]
  onSubmit: (answers: { field: string; value: unknown }[]) => void
  onSkip: (answers: { field: string; value: unknown }[]) => void
  busy?: boolean
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const set = (field: string, value: string) =>
    setAnswers((prev) => ({ ...prev, [field]: value }))

  const answered = questions.filter((q) => (answers[q.field] ?? '').trim() !== '')
  // Round 1 decides which standards apply; round 2 only sharpens the analysis.
  const essential = questions.every((q) => (q.priority ?? 1) === 1)

  return (
    <section className="card border-violet-200 bg-gradient-to-b from-violet-50/60 to-white p-6">
      <header className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-600">
          <MessageCircleQuestion className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-base font-bold text-ink-900">
            {essential ? 'A few details before we search' : 'Optional: sharpen the analysis'}
          </h3>
          <p className="mt-0.5 text-sm leading-relaxed text-ink-600">
            {essential
              ? 'These answers change which standards apply. Rather than assume them, the platform asks — you can also continue without answering.'
              : 'The decisive questions are answered. These extra values are not needed to find the standards, but they let the gap analyzer assess more requirements instead of reporting them as Unknown.'}
          </p>
        </div>
      </header>

      <div className="mt-5 space-y-5">
        {questions.map((q) => (
          <div key={q.field}>
            <label className="block text-sm font-semibold text-ink-900" htmlFor={q.field}>
              {q.question}
            </label>
            <p className="mt-0.5 text-xs leading-relaxed text-ink-500">{q.why_it_matters}</p>

            {q.options.length > 0 ? (
              <div className="mt-2.5 flex flex-wrap gap-2">
                {q.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => set(q.field, option)}
                    className={`rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors ${
                      answers[q.field] === option
                        ? 'border-violet-500 bg-violet-600 text-white'
                        : 'border-ink-200 bg-white text-ink-700 hover:border-violet-300 hover:bg-violet-50'
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            ) : (
              <div className="mt-2.5 flex items-center gap-2">
                <input
                  id={q.field}
                  className="field max-w-xs"
                  type={q.input_type === 'number' ? 'number' : 'text'}
                  value={answers[q.field] ?? ''}
                  onChange={(e) => set(q.field, e.target.value)}
                  placeholder={q.unit ? `Value in ${q.unit}` : 'Your answer'}
                />
                {q.unit && <span className="text-sm font-medium text-ink-500">{q.unit}</span>}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2.5">
        <button
          className="btn-primary"
          disabled={busy || answered.length === 0}
          onClick={() =>
            onSubmit(answered.map((q) => ({ field: q.field, value: answers[q.field] })))
          }
        >
          Save {answered.length > 0 ? `${answered.length} answer${answered.length > 1 ? 's' : ''}` : 'answers'}
          <ArrowRight className="h-4 w-4" />
        </button>
        {/* Skipping still keeps whatever the user already typed - it only stops
            the platform asking for the rest. */}
        <button
          className="btn-secondary"
          disabled={busy}
          onClick={() => onSkip(answered.map((q) => ({ field: q.field, value: answers[q.field] })))}
        >
          <SkipForward className="h-4 w-4" />
          {essential ? 'Continue with current information' : 'Skip these'}
        </button>
        <p className="w-full text-xs text-ink-400 sm:w-auto sm:flex-1">
          Skipped values are reported as <span className="font-semibold">Unknown</span>, never assumed.
        </p>
      </div>
    </section>
  )
}
