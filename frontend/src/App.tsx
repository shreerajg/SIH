import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { LanguageProvider } from '@/contexts/LanguageContext'
import { Layout } from '@/components/Layout'
import { Landing } from '@/pages/Landing'
import { Manufacturer } from '@/pages/Manufacturer'
import { ProductAnalysis } from '@/pages/ProductAnalysis'
import { StandardsDiscovery } from '@/pages/StandardsDiscovery'
import { GapAnalysis } from '@/pages/GapAnalysis'
import { ComplianceTwin } from '@/pages/ComplianceTwin'
import { CertificationProcess } from '@/pages/CertificationProcess'
import { Consumer } from '@/pages/Consumer'
import { Hallmarking } from '@/pages/Hallmarking'
import { Assistant } from '@/pages/Assistant'
import { DynamicChatPage } from '@/pages/DynamicChatPage'
import { StandardsBrowser, StandardDetailPage } from '@/pages/StandardsBrowser'
import { StandardsGraph } from '@/pages/StandardsGraph'
import { Trust } from '@/pages/Trust'

export function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/manufacturer" element={<Manufacturer />} />
            <Route path="/product-analysis/:productId" element={<ProductAnalysis />} />
            <Route path="/product/:productId/standards" element={<StandardsDiscovery />} />
            <Route path="/product/:productId/gap-analysis" element={<GapAnalysis />} />
            <Route path="/product/:productId/compliance" element={<ComplianceTwin />} />
            <Route
              path="/product/:productId/certification-process"
              element={<CertificationProcess />}
            />
            <Route path="/consumer" element={<Consumer />} />
            <Route path="/hallmarking" element={<Hallmarking />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/chat" element={<DynamicChatPage />} />
            <Route path="/standards" element={<StandardsBrowser />} />
            <Route path="/graph" element={<StandardsGraph />} />
            <Route path="/standards/:standardId" element={<StandardDetailPage />} />
            <Route path="/trust" element={<Trust />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </LanguageProvider>
  )
}
