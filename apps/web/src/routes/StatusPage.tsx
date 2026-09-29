import { Button } from '../components/Button'
import { Chip } from '../components/Chip'
import { PageShell } from '../components/PageShell'
import { useReadiness } from '../features/health/useReadiness'

const content = {
  loading: {
    title: 'Verificando o radar',
    description: 'Conectando à API local para confirmar que o ambiente está pronto.',
    tone: 'border-line-strong bg-info-surface text-info-ink',
    label: 'Consultando /api/health/ready',
  },
  error: {
    title: 'A API não está disponível',
    description:
      'Inicie os serviços locais e tente novamente. O dashboard volta a consultar a API quando você recarregar a página.',
    tone: 'border-danger-line bg-danger-surface-strong text-danger-ink',
    label: 'Conexão pendente',
  },
  degraded: {
    title: 'Radar disponível com recursos limitados',
    description:
      'A API está respondendo, mas uma dependência está indisponível. Coleta e análise podem ficar parcialmente limitadas.',
    tone: 'border-warning-line bg-warning-surface-strong text-warning-ink-strong',
    label: 'Estado degradado',
  },
  ready: {
    title: 'Radar pronto para começar',
    description:
      'A base local está conectada. O catálogo de empresas já pode ser importado e consultado no dashboard.',
    tone: 'border-success-line bg-success-surface-strong text-success-ink-strong',
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
        <div role="status">
          <Chip dot tone={view.tone}>
            {view.label}
          </Chip>
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
