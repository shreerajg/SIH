import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { api } from '@/lib/api'
import { LanguageSelector } from '@/components/LanguageSelector'
import { useLanguage } from '@/contexts/LanguageContext'
import { useTranslation } from '@/lib/translations'
import type { HealthResponse } from '@/lib/types'

export function Layout() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [offline, setOffline] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const { language } = useLanguage()
  const t = useTranslation(language)

  const getNavItems = () => [
    { to: '/manufacturer', label: t.nav.manufacturer },
    { to: '/consumer', label: t.nav.consumer },
    { to: '/hallmarking', label: t.nav.hallmarking },
    { to: '/chat', label: t.nav.chat },
    { to: '/standards', label: t.nav.standards },
    { to: '/graph', label: t.nav.graph },
    { to: '/trust', label: t.nav.trust },
  ]

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setOffline(true))
  }, [])

  useEffect(() => setMenuOpen(false), [location.pathname])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-ink-200 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-extrabold text-white">
              BI
            </span>
            <span className="hidden text-sm font-extrabold tracking-tight text-ink-900 sm:block">
              BIS Standards Intelligence
            </span>
          </Link>

          <nav className="ml-auto hidden items-center gap-1 md:flex">
            {getNavItems().map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                    isActive ? 'bg-ink-100 text-ink-900' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-800'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <LanguageSelector />
            <button
              className="btn-ghost btn-sm md:hidden"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Toggle navigation"
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="border-t border-ink-200 bg-white px-4 py-2 md:hidden">
            {getNavItems().map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2.5 text-sm font-semibold ${
                    isActive ? 'bg-ink-100 text-ink-900' : 'text-ink-600'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      {offline && (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-2.5 text-center text-sm text-rose-800">
          Backend unreachable. Start it with{' '}
          <code className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-xs">
            cd backend &amp;&amp; uvicorn app.main:app --reload --port 8000
          </code>
        </div>
      )}

      {health && health.corpus.starved && (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-center text-xs font-medium text-rose-900">
          {health.corpus.corpus_mode_message}
        </div>
      )}

      <main className="flex-1">
        <Outlet context={{ health }} />
      </main>
    </div>
  )
}
