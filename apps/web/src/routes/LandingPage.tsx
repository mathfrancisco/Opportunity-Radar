import { SignInButton, SignUpButton } from '@clerk/react'

export function LandingPage() {
  return (
    <main className="min-h-screen bg-canvas px-5 py-16 text-ink sm:px-8 sm:py-24">
      <section className="mx-auto max-w-3xl">
        <p className="text-sm font-semibold text-accent-ink">Opportunity Radar</p>
        <h1 className="mt-4 max-w-2xl text-page-title">
          Encontre oportunidades alinhadas à sua carreira.
        </h1>
        <p className="mt-4 max-w-2xl text-body text-subtle">
          Organize vagas, compare cada oportunidade com seu perfil e acompanhe suas candidaturas
          em um só lugar.
        </p>
        <ul className="mt-8 grid gap-4 text-sm text-subtle sm:grid-cols-3">
          <li className="rounded-panel border border-line bg-surface p-4">
            Acompanhe vagas relevantes em uma inbox organizada.
          </li>
          <li className="rounded-panel border border-line bg-surface p-4">
            Entenda como cada vaga combina com seu perfil.
          </li>
          <li className="rounded-panel border border-line bg-surface p-4">
            Gerencie etapas e próximas ações da sua busca.
          </li>
        </ul>
        <div className="mt-8 flex flex-wrap gap-3">
          <SignInButton fallbackRedirectUrl="/" mode="redirect">
            <button className="min-h-11 rounded-control border border-line-strong bg-surface px-5 text-sm font-semibold text-ink" type="button">
              Entrar
            </button>
          </SignInButton>
          <SignUpButton fallbackRedirectUrl="/" mode="redirect">
            <button className="min-h-11 rounded-control bg-accent px-5 text-sm font-semibold text-surface" type="button">
              Criar conta
            </button>
          </SignUpButton>
        </div>
      </section>
    </main>
  )
}
