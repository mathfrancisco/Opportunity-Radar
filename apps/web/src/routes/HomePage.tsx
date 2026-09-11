import { useReadiness } from '../features/health/useReadiness'
import { Link } from 'react-router-dom'

const content = {
  loading: {
    title: 'Verificando o radar',
    description: 'Conectando à API local para confirmar que o ambiente está pronto.',
    tone: 'loading',
  },
  error: {
    title: 'A API não está disponível',
    description: 'Inicie os serviços locais e tente novamente. O dashboard volta a consultar a API quando você recarregar a página.',
    tone: 'error',
  },
  degraded: {
    title: 'Radar disponível com recursos limitados',
    description: 'A API está respondendo, mas uma dependência está indisponível. Coleta e análise podem ficar parcialmente limitadas.',
    tone: 'degraded',
  },
  ready: {
    title: 'Radar pronto para começar',
    description: 'A base local está conectada. O catálogo de empresas já pode ser importado e consultado no dashboard.',
    tone: 'ready',
  },
} as const

export function HomePage() {
  const readiness = useReadiness()
  const state = readiness.isPending
    ? 'loading'
    : readiness.isError
      ? 'error'
      : readiness.data.state
  const view = content[state]

  return (
    <main className="min-h-screen bg-[#f2f5ef] px-5 py-7 text-[#17322d] sm:px-10 sm:py-10">
      <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-5xl flex-col justify-between rounded-[2rem] border border-[#ced8ce] bg-[#fbfcf8] p-7 shadow-[0_24px_70px_rgba(23,50,45,0.10)] sm:p-12">
        <header className="flex flex-wrap items-center justify-between gap-4" aria-label="Opportunity Radar">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-[#d7f06f] text-lg font-black">◉</span>
          <span className="text-lg font-semibold tracking-tight">Opportunity Radar</span>
          <nav aria-label="Navegação principal" className="flex gap-4 text-sm font-medium">
            <Link aria-current="page" className="text-[#17322d] underline decoration-[#d7f06f] decoration-2 underline-offset-4" to="/">Status</Link>
            <Link className="text-[#547068] hover:text-[#17322d]" to="/companies">Empresas</Link>
          </nav>
        </header>

        <section aria-live="polite" className="max-w-2xl py-16 sm:py-24">
          <p className="mb-5 text-sm font-medium text-[#547068]">Ambiente local</p>
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-[-0.04em] sm:text-6xl">{view.title}</h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-[#547068]">{readiness.data?.detail ?? view.description}</p>
          <div className={`status status-${view.tone}`}>
            <span aria-hidden="true" className="status-dot" />
            {state === 'loading' ? 'Consultando /api/health/ready' : state === 'error' ? 'Conexão pendente' : state === 'degraded' ? 'Estado degradado' : 'API pronta'}
          </div>
          {readiness.isError && (
            <button className="retry-button" onClick={() => void readiness.refetch()} type="button">
              Tentar novamente
            </button>
          )}
        </section>

        <footer className="border-t border-[#dce4dc] pt-5 text-sm text-[#6d827b]">
          Descubra oportunidades, preserve evidências e decida com contexto.
        </footer>
      </div>
    </main>
  )
}
