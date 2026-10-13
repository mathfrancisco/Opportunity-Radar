import { SignIn, SignUp, useAuth } from '@clerk/react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthPending, RequireOwnerUi, RequireSignedIn } from './RouteGuards'
import { CompaniesPage } from '../routes/CompaniesPage'
import { CompanyDetailPage } from '../routes/CompanyDetailPage'
import { HomologationQueuePage } from '../routes/HomologationQueuePage'
import { InboxPage } from '../routes/InboxPage'
import { LandingPage } from '../routes/LandingPage'
import { OpportunityDetailPage } from '../routes/OpportunityDetailPage'
import { OverviewPage } from '../routes/OverviewPage'
import { PipelinePage } from '../routes/PipelinePage'
import { ProfilePage } from '../routes/ProfilePage'
import { SourcesPage } from '../routes/SourcesPage'
import { StatusPage } from '../routes/StatusPage'

function HomeRoute() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <AuthPending />
  return isSignedIn ? (
    <RequireSignedIn>
      <OverviewPage />
    </RequireSignedIn>
  ) : (
    <LandingPage />
  )
}

function AuthenticationRoute({ kind }: { kind: 'sign-in' | 'sign-up' }) {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <AuthPending />
  if (isSignedIn) return <Navigate replace to="/" />
  return kind === 'sign-in' ? <SignIn /> : <SignUp />
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/sign-in/*" element={<AuthenticationRoute kind="sign-in" />} />
      <Route path="/sign-up/*" element={<AuthenticationRoute kind="sign-up" />} />
      <Route path="/inbox" element={<RequireSignedIn><InboxPage /></RequireSignedIn>} />
      <Route path="/opportunities/:opportunityId" element={<RequireSignedIn><OpportunityDetailPage /></RequireSignedIn>} />
      <Route path="/applications" element={<RequireSignedIn><PipelinePage /></RequireSignedIn>} />
      <Route path="/companies" element={<RequireOwnerUi><CompaniesPage /></RequireOwnerUi>} />
      <Route path="/companies/:companyId" element={<RequireOwnerUi><CompanyDetailPage /></RequireOwnerUi>} />
      <Route path="/sources" element={<RequireOwnerUi><SourcesPage /></RequireOwnerUi>} />
      <Route path="/sources/homologation-queue" element={<RequireOwnerUi><HomologationQueuePage /></RequireOwnerUi>} />
      <Route path="/profile" element={<RequireSignedIn><ProfilePage /></RequireSignedIn>} />
      <Route path="/status" element={<RequireOwnerUi><StatusPage /></RequireOwnerUi>} />
      <Route path="*" element={<HomeRoute />} />
    </Routes>
  )
}
