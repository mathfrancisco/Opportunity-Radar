import { Route, Routes } from 'react-router-dom'
import { CompaniesPage } from '../routes/CompaniesPage'
import { CompanyDetailPage } from '../routes/CompanyDetailPage'
import { InboxPage } from '../routes/InboxPage'
import { OpportunityDetailPage } from '../routes/OpportunityDetailPage'
import { OverviewPage } from '../routes/OverviewPage'
import { ProfilePage } from '../routes/ProfilePage'
import { SourcesPage } from '../routes/SourcesPage'
import { StatusPage } from '../routes/StatusPage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} />
      <Route path="/companies" element={<CompaniesPage />} />
      <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
      <Route path="/sources" element={<SourcesPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route path="*" element={<OverviewPage />} />
    </Routes>
  )
}
