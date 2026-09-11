import { Route, Routes } from 'react-router-dom'
import { CompaniesPage } from '../routes/CompaniesPage'
import { HomePage } from '../routes/HomePage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/companies" element={<CompaniesPage />} />
      <Route path="*" element={<HomePage />} />
    </Routes>
  )
}
