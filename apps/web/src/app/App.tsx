import { SignIn, SignUp, useAuth } from '@clerk/react'
import { type ReactNode } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { BrandMark } from '../components/ui/BrandMark'
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
  const form = kind === 'sign-in' ? (
    <SignIn fallbackRedirectUrl="/" path="/sign-in" routing="path" signUpUrl="/sign-up" />
  ) : (
    <SignUp fallbackRedirectUrl="/" path="/sign-up" routing="path" signInUrl="/sign-in" />
  )

  return <AuthenticationShell>{form}</AuthenticationShell>
}

function AuthenticationShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-canvas px-5 py-6 text-ink sm:px-8 sm:py-8">
      <div className="mx-auto grid min-h-[calc(100vh-3rem)] max-w-6xl overflow-hidden rounded-panel border border-line bg-surface lg:grid-cols-[minmax(0,0.85fr)_minmax(24rem,0.65fr)]">
        <section className="flex flex-col justify-between bg-sidebar p-6 sm:p-10">
          <div>
            <Link className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold tracking-tight text-ink" to="/">
              <BrandMark />
            </Link>
            <p className="mt-14 text-caption font-semibold text-accent-ink">Seu espaço de decisão</p>
            <h1 className="mt-4 max-w-md text-3xl font-semibold tracking-tight sm:text-4xl">Organize a busca antes da próxima candidatura.</h1>
            <p className="mt-4 max-w-md text-body-sm text-subtle">Retome vagas, compare o que importa e acompanhe cada próxima ação em um só lugar.</p>
          </div>
          <Link className="mt-12 inline-flex min-h-11 w-fit items-center text-sm font-semibold text-accent-ink hover:text-accent-hover" to="/">← Voltar para a página inicial</Link>
        </section>
        <section aria-label="Acesso à conta" className="flex items-center justify-center p-4 sm:p-8">
          <div className="w-full max-w-md">{children}</div>
        </section>
      </div>
    </main>
  )
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
