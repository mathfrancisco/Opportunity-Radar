import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
import { PageShell } from '../components/PageShell'
import { useReadiness } from '../features/health/useReadiness'

const content = {
  loading: {
    title: 'Verificando o radar',
    description: 'Conectando à API local para confirmar que o ambiente está pronto.',
    tone: 'border-line-strong bg-info-surface text-info-ink',
    label: 'Consultando /api/health/ready',
    nextAction: 'Aguarde a confirmação dos serviços antes de iniciar uma coleta.',
  },
  error: {
    title: 'A API não está disponível',
    description:
      'Inicie os serviços locais e tente novamente. O dashboard volta a consultar a API quando você recarregar a página.',
    tone: 'border-danger-line bg-danger-surface-strong text-danger-ink',
    label: 'Conexão pendente',
    nextAction: 'Inicie o ambiente local e tente a verificação novamente.',
  },
  degraded: {
    title: 'Radar disponível com recursos limitados',
    description:
      'A API está respondendo, mas o ambiente não confirmou todos os sinais de saúde. Algumas operações podem ficar limitadas.',
    tone: 'border-warning-line bg-warning-surface-strong text-warning-ink-strong',
    label: 'Estado degradado',
    nextAction: 'Confira a configuração e a saúde dos serviços antes de iniciar uma coleta.',
  },
  ready: {
    title: 'Radar pronto para começar',
    description:
      'A base local está conectada. O catálogo de empresas já pode ser importado e consultado no dashboard.',
    tone: 'border-success-line bg-success-surface-strong text-success-ink-strong',
    label: 'API pronta',
    nextAction: 'Revise as fontes ativas e inicie uma busca quando o catálogo estiver preparado.',
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
      <div className="mt-8 grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <Card className="p-6">
          <p className="text-caption font-medium text-muted">Prontidão do ambiente</p>
          <div className="mt-3" role="status">
            <Chip dot tone={view.tone}>
              {view.label}
            </Chip>
          </div>
          <p className="mt-4 text-sm text-subtle">{view.description}</p>
        </Card>

        <Card className="p-6">
          <h2 className="text-section">Próxima ação</h2>
          <p className="mt-2 text-sm text-subtle">{view.nextAction}</p>
          {readiness.isError ? (
            <Button className="mt-5" onClick={() => void readiness.refetch()} variant="secondary">
              Tentar novamente
            </Button>
          ) : state === 'ready' ? (
            <Link
              className="mt-5 inline-flex text-sm font-medium underline decoration-accent decoration-2 underline-offset-4"
              to="/sources"
            >
              Ver fontes
            </Link>
          ) : null}
        </Card>
      </div>

      <section className="mt-6" aria-label="Como o estado é calculado">
        <h2 className="text-section">Como interpretar este estado</h2>
        <Card className="mt-3 p-4">
          <p className="text-sm text-subtle">
            A prontidão confirma que a API e a conexão com o banco de dados estão disponíveis.
            {state === 'ready'
              ? ' O ambiente está pronto para consultar o catálogo local.'
              : state === 'loading'
                ? ' A confirmação ainda está em andamento.'
                : state === 'degraded'
                  ? ' API e banco confirmados; a IA está indisponível.'
                  : ' A confirmação de prontidão ainda não está disponível.'}
          </p>
        </Card>
      </section>
    </PageShell>
  )
}
