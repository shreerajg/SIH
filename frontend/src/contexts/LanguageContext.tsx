import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

export type Language =
  | 'en'  // English
  | 'hi'  // Hindi
  | 'ta'  // Tamil
  | 'te'  // Telugu
  | 'kn'  // Kannada
  | 'ml'  // Malayalam
  | 'bn'  // Bengali
  | 'gu'  // Gujarati
  | 'mr'  // Marathi
  | 'pa'  // Punjabi
  | 'or'  // Odia
  | 'as'  // Assamese

export const LANGUAGES = {
  en: { name: 'English', nativeName: 'English' },
  hi: { name: 'Hindi', nativeName: 'हिंदी' },
  ta: { name: 'Tamil', nativeName: 'தமிழ்' },
  te: { name: 'Telugu', nativeName: 'తెలుగు' },
  kn: { name: 'Kannada', nativeName: 'ಕನ್ನಡ' },
  ml: { name: 'Malayalam', nativeName: 'മലയാളം' },
  bn: { name: 'Bengali', nativeName: 'বাংলা' },
  gu: { name: 'Gujarati', nativeName: 'ગુજરાતી' },
  mr: { name: 'Marathi', nativeName: 'मराठी' },
  pa: { name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ' },
  or: { name: 'Odia', nativeName: 'ଓଡ଼ିଆ' },
  as: { name: 'Assamese', nativeName: 'অসমীয়া' },
}

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem('app-language')
    return (saved as Language) || 'en'
  })

  useEffect(() => {
    localStorage.setItem('app-language', language)
    document.documentElement.lang = language
  }, [language])

  const setLanguage = (lang: Language) => {
    setLanguageState(lang)
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider')
  }
  return context
}
