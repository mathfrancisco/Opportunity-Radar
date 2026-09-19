import { Route, Routes } from 'react-router-dom'
import { CompaniesPage } from '../routes/CompaniesPage'
import { InboxPage } from '../routes/InboxPage'
import { OverviewPage } from '../routes/OverviewPage'
import { StatusPage } from '../routes/StatusPage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/companies" element={<CompaniesPage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route path="*" element={<OverviewPage />} />
    </Routes>
  )
}
