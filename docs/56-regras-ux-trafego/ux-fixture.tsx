import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { InboxPage } from '../../apps/web/src/routes/InboxPage'
import { OpportunityDetailPage } from '../../apps/web/src/routes/OpportunityDetailPage'
import { OverviewPage } from '../../apps/web/src/routes/OverviewPage'
import { PipelinePage } from '../../apps/web/src/routes/PipelinePage'
import { createQueryClient } from '../../apps/web/src/lib/queryClient'
import { setAuthSession, setAuthTokenGetter } from '../../apps/web/src/lib/api'
import '../../apps/web/src/styles.css'

const params = new URLSearchParams(location.search)
const route = params.get('route') ?? 'inbox'
const state = params.get('state') ?? 'loaded'
const entries: Record<string, string> = {
  inbox: '/inbox', detail: '/opportunities/ux-opportunity', pipeline: '/applications', overview: '/',
}
const queryClient = createQueryClient()
queryClient.setDefaultOptions({ queries: { retry: false, staleTime: 0 } })
setAuthSession('offline-ux-fixture', true)
setAuthTokenGetter(async () => 'offline-ux-fixture')

document.documentElement.dataset.uxFixture = 'true'
document.documentElement.dataset.uxRoute = route
document.documentElement.dataset.uxState = state

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entries[route] ?? entries.inbox]}>
        <Routes>
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} />
          <Route path="/applications" element={<PipelinePage />} />
          <Route path="/" element={<OverviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  </StrictMode>,
)
