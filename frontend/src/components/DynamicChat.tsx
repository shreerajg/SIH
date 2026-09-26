import { useEffect, useRef, useState } from 'react'
import { api, apiError } from '@/lib/api'
import { useLanguage, LANGUAGES } from '@/contexts/LanguageContext'
import type { ChatSource } from '@/lib/types'
import { AlertCircle, ExternalLink, Search, Shield, Sparkles } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  answerable?: boolean
  timestamp: Date
}

// Render **bold**, bullet points, and newlines from the AI answer
function AnswerText({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="space-y-1 leading-relaxed">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-2" />

        // Render **bold** markdown
        const parts = line.split(/(\*\*[^*]+\*\*)/g)
        const rendered = parts.map((part, j) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={j}>{part.slice(2, -2)}</strong>
          }
          return <span key={j}>{part}</span>
        })

        // Bullet points
        if (line.trim().startsWith('•') || line.trim().startsWith('-')) {
          return (
            <div key={i} className="ml-3 flex gap-2">
              <span className="mt-1 text-indigo-500">•</span>
              <span>{rendered}</span>
            </div>
          )
        }

        return <div key={i}>{rendered}</div>
      })}
    </div>
  )
}

const PLACEHOLDERS: Record<string, string> = {
  en: 'Ask about BIS standards, certification, testing...',
  hi: 'BIS मानकों के बारे में पूछें...',
  ta: 'BIS தரநிலைகள் பற்றி கேளுங்கள்...',
  te: 'BIS ప్రమాణాల గురించి అడగండి...',
  kn: 'BIS ಮಾನದಂಡಗಳ ಬಗ್ಗೆ ಕೇಳಿ...',
  ml: 'BIS നിലവാരങ്ങളെക്കുറിച്ച് ചോദിക്കുക...',
  bn: 'BIS মানদণ্ড সম্পর্কে জিজ্ঞাসা করুন...',
  gu: 'BIS ધોરણો વિશે પૂછો...',
  mr: 'BIS मानकांबद्दल विचारा...',
  pa: 'BIS ਮਾਪਦੰਡਾਂ ਬਾਰੇ ਪੁੱਛੋ...',
  or: 'BIS ମାନ ବିଷୟରେ ପଚାରନ୍ତୁ...',
  as: 'BIS মানদণ্ডৰ বিষয়ে সোধক...',
}

const SEND_LABELS: Record<string, string> = {
  en: 'Send', hi: 'भेजें', ta: 'அனுப்பு', te: 'పంపు',
  kn: 'ಕಳುಹಿಸಿ', ml: 'അയയ്ക്കുക', bn: 'পাঠান', gu: 'મોકલો',
  mr: 'पाठवा', pa: 'ਭੇਜੋ', or: 'ପଠାନ୍ତୁ', as: 'পঠাওক',
}

const SEARCHING_LABELS: Record<string, string> = {
  en: 'Searching BIS sources...',
  hi: 'BIS स्रोतों में खोज रहे हैं...',
  ta: 'BIS ஆதாரங்களில் தேடுகிறோம்...',
  te: 'BIS మూలాల్లో శోధిస్తోంది...',
  kn: 'BIS ಮೂಲಗಳಲ್ಲಿ ಹುಡುಕಲಾಗುತ್ತಿದೆ...',
  ml: 'BIS ഉറവിടങ്ങളിൽ തിരയുന്നു...',
  bn: 'BIS উৎসগুলিতে অনুসন্ধান করছি...',
  gu: 'BIS સ્ત્રોતો શોધી રહ્યા છીએ...',
  mr: 'BIS स्रोतांमध्ये शोधत आहे...',
  pa: 'BIS ਸਰੋਤਾਂ ਵਿੱਚ ਖੋਜ ਕਰ ਰਹੇ ਹਾਂ...',
}

export function DynamicChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const { language } = useLanguage()
  const [conversationId] = useState(() => `chat-${Date.now()}`)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await api.chatMessage({
        message: input,
        conversation_id: conversationId,
        language,
      })

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          answerable: response.answerable,
          timestamp: new Date(),
        },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${apiError(error)}`,
          answerable: false,
          timestamp: new Date(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const currentLang = LANGUAGES[language]

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-gray-50">
      {/* Header */}
      <div className="border-b bg-white px-6 py-4 shadow-sm">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-xl font-bold text-gray-900">BIS Knowledge Assistant</h1>
          <p className="text-sm text-gray-500">
            Live retrieval from official BIS sources · Responding in{' '}
            <span className="font-medium text-indigo-600">{currentLang.nativeName}</span>
          </p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.length === 0 && (
            <div className="mt-12 text-center">
              <Sparkles className="mx-auto h-10 w-10 text-indigo-400" />
              <h2 className="mt-4 text-lg font-semibold text-gray-800">
                Ask me anything about BIS standards
              </h2>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {[
                  'Standards for pressure cookers?',
                  'BIS certification for electric irons?',
                  'IS number for stainless steel pipes?',
                  'How to apply for BIS licence?',
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="rounded-lg border bg-white px-4 py-3 text-left text-sm text-gray-700 shadow-sm hover:border-indigo-300 hover:bg-indigo-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              {msg.role === 'assistant' && (
                <div className="mr-3 mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                  BIS
                </div>
              )}
              <div className={`max-w-2xl rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'border bg-white text-gray-900 shadow-sm'
              }`}>
                {msg.role === 'user' ? (
                  <p>{msg.content}</p>
                ) : (
                  <AnswerText text={msg.content} />
                )}

                {/* Sources - compact cards */}
                {msg.sources && msg.sources.length > 0 && (
                  <details className="mt-4 border-t pt-3">
                    <summary className="cursor-pointer text-xs font-semibold text-gray-500 hover:text-gray-700">
                      {msg.sources.length} Sources Used
                    </summary>
                    <div className="mt-2 space-y-1">
                      {msg.sources.map((source) => (
                        <a
                          key={source.id}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 rounded-lg border bg-gray-50 px-3 py-2 text-xs hover:bg-gray-100"
                        >
                          <span className="font-mono text-gray-400">[{source.id}]</span>
                          {source.official && <Shield className="h-3 w-3 shrink-0 text-green-600" />}
                          <span className="flex-1 truncate font-medium text-gray-800">{source.title}</span>
                          <ExternalLink className="h-3 w-3 shrink-0 text-gray-400" />
                        </a>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                BIS
              </div>
              <div className="flex items-center gap-2 rounded-2xl border bg-white px-4 py-3 shadow-sm">
                <Search className="h-4 w-4 animate-pulse text-indigo-500" />
                <span className="text-sm text-gray-500">
                  {SEARCHING_LABELS[language] || SEARCHING_LABELS['en']}
                </span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t bg-white px-4 py-4 shadow-lg">
        <form onSubmit={handleSubmit} className="mx-auto max-w-3xl">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={PLACEHOLDERS[language] || PLACEHOLDERS['en']}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {SEND_LABELS[language] || 'Send'}
            </button>
          </div>
          <p className="mt-2 flex items-center gap-1 text-xs text-gray-400">
            <AlertCircle className="h-3 w-3" />
            Answers are sourced from official BIS documents. Verify critical decisions directly with BIS.
          </p>
        </form>
      </div>
    </div>
  )
}
