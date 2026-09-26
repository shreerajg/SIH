import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { Landing } from '@/pages/Landing'
import { Manufacturer } from '@/pages/Manufacturer'
import { ProductAnalysis } from '@/pages/ProductAnalysis'
import { StandardsDiscovery } from '@/pages/StandardsDiscovery'
import { GapAnalysis } from '@/pages/GapAnalysis'
import { ComplianceTwin } from '@/pages/ComplianceTwin'
import { Consumer } from '@/pages/Consumer'
import { Assistant } from '@/pages/Assistant'
import { StandardsBrowser, StandardDetailPage } from '@/pages/StandardsBrowser'
import { StandardsGraph } from '@/pages/StandardsGraph'
import { Trust } from '@/pages/Trust'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Landing />} />
          <Route path="/manufacturer" element={<Manufacturer />} />
          <Route path="/product-analysis/:productId" element={<ProductAnalysis />} />
          <Route path="/product/:productId/standards" element={<StandardsDiscovery />} />
          <Route path="/product/:productId/gap-analysis" element={<GapAnalysis />} />
          <Route path="/product/:productId/compliance" element={<ComplianceTwin />} />
          <Route path="/consumer" element={<Consumer />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/standards" element={<StandardsBrowser />} />
          <Route path="/graph" element={<StandardsGraph />} />
          <Route path="/standards/:standardId" element={<StandardDetailPage />} />
          <Route path="/trust" element={<Trust />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
