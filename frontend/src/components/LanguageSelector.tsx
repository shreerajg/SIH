import { useState, useRef, useEffect } from 'react'
import { Check, ChevronDown, Globe } from 'lucide-react'
import { useLanguage, LANGUAGES, type Language } from '@/contexts/LanguageContext'

export function LanguageSelector() {
  const { language, setLanguage } = useLanguage()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  const handleLanguageChange = (lang: Language) => {
    setLanguage(lang)
    setIsOpen(false)
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        aria-label="Select language"
      >
        <Globe className="h-4 w-4" />
        <span className="hidden sm:inline">{LANGUAGES[language].nativeName}</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-56 rounded-lg border border-gray-200 bg-white shadow-lg">
          <div className="max-h-80 overflow-y-auto py-1">
            {(Object.keys(LANGUAGES) as Language[]).map((lang) => (
              <button
                key={lang}
                onClick={() => handleLanguageChange(lang)}
                className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-gray-50 ${
                  language === lang ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700'
                }`}
              >
                <div className="flex flex-col">
                  <span className="font-medium">{LANGUAGES[lang].nativeName}</span>
                  <span className="text-xs text-gray-500">{LANGUAGES[lang].name}</span>
                </div>
                {language === lang && <Check className="h-4 w-4 text-indigo-600" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
