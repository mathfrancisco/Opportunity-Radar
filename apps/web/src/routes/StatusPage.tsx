import { Button } from '../components/Button'
import { PageShell } from '../components/PageShell'
import { useReadiness } from '../features/health/useReadiness'

const content = {
  loading: {
    title: 'Verificando o radar',
    description: 'Conectando à API local para confirmar que o ambiente está pronto.',
    tone: 'loading',
    label: 'Consultando /api/health/ready',
  },
  error: {
    title: 'A API não está disponível',
    description:
      'Inicie os serviços locais e tente novamente. O dashboard volta a consultar a API quando você recarregar a página.',
    tone: 'error',
    label: 'Conexão pendente',
  },
  degraded: {
    title: 'Radar disponível com recursos limitados',
    description:
      'A API está respondendo, mas uma dependência está indisponível. Coleta e análise podem ficar parcialmente limitadas.',
    tone: 'degraded',
    label: 'Estado degradado',
  },
  ready: {
    title: 'Radar pronto para começar',
    description:
      'A base local está conectada. O catálogo de empresas já pode ser importado e consultado no dashboard.',
    tone: 'ready',
    label: 'API pronta',
  },
} as const

export function StatusPage() {
  const readiness = useReadiness()
  const state = readiness.isPending
    ? 'loading'
    : readiness.isError
      ? 'error'
      : readiness.data.state
  const view = content[state]

  return (
    <PageShell
      current="/status"
      eyebrow="Ambiente local"
      title={view.title}
      description={readiness.data?.detail ?? view.description}
      footer="Descubra oportunidades, preserve evidências e decida com contexto."
    >
      <div className="mt-6">
        {/* O estado é o conteúdo desta tela, e não um substituto enquanto ela carrega. */}
        <div className={`status status-${view.tone}`} role="status">
          <span aria-hidden="true" className="status-dot" />
          {view.label}
        </div>
        {readiness.isError && (
          <div>
            <Button className="mt-4" onClick={() => void readiness.refetch()}>
              Tentar novamente
            </Button>
          </div>
        )}
      </div>
    </PageShell>
  )
}
