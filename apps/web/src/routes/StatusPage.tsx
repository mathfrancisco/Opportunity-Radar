import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Chip } from '../components/Chip'
import { DataTable } from '../components/DataTable'
import { PageShell } from '../components/PageShell'
import { StatusBadge } from '../components/StatusBadge'
import { Unavailable } from '../components/Unavailable'
import { SecondaryText, PrimaryText } from '../components/cells'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { useReadiness } from '../features/health/useReadiness'
import { type SourceHealth } from '../features/sources/api'
import { runStatusLabels, runStatusTones } from '../features/sources/states'
import { useSourceHealth } from '../features/sources/useSources'

const content = {
  loading: {
    title: 'Verificando o radar',
    description: 'Conectando à API para confirmar que o ambiente está pronto.',
    tone: 'border-line-strong bg-info-surface text-info-ink',
    label: 'Consultando /api/health/ready',
    nextAction: 'Aguarde a confirmação dos serviços antes de iniciar uma coleta.',
  },
  error: {
    title: 'A API não está disponível',
    description:
      'Confirme que a API está no ar e tente novamente. O painel volta a consultar a API quando você recarregar a página.',
    tone: 'border-danger-line bg-danger-surface-strong text-danger-ink',
    label: 'Conexão pendente',
    nextAction: 'Confirme que a API está no ar e tente a verificação novamente.',
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
      'A API e o banco de dados estão conectados. O catálogo de empresas já pode ser importado e consultado no painel.',
    tone: 'border-success-line bg-success-surface-strong text-success-ink-strong',
    label: 'API pronta',
    nextAction: 'Revise as fontes ativas e inicie uma busca quando o catálogo estiver preparado.',
  },
} as const

function formatDate(value: string | null) {
  if (!value) return <Unavailable reason="nunca executada" />
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? (
    <Unavailable reason="data inválida" />
  ) : (
    parsed.toLocaleString('pt-BR')
  )
}

function itemsText(source: SourceHealth) {
  if (source.lastRunItemsSeen === null) return <Unavailable reason="nunca executada" />
  const parts = [`${source.lastRunItemsPersisted ?? 0} gravados / ${source.lastRunItemsSeen} vistos`]
  if ((source.lastRunItemsSkipped ?? 0) > 0) parts.push(`${source.lastRunItemsSkipped} repetidos`)
  if ((source.lastRunItemsInvalid ?? 0) > 0) parts.push(`${source.lastRunItemsInvalid} inválidos`)
  return parts.join(' · ')
}

/** R55-D6: the last run of every source, from the existing source health API. */
function SourceMetrics() {
  const health = useSourceHealth()

  let body
  if (health.isPending) {
    body = <LoadingState className="mt-3">Carregando métricas por fonte…</LoadingState>
  } else if (health.isError) {
    body = (
      <ErrorState className="mt-3" onRetry={() => void health.refetch()}>
        Não foi possível carregar as métricas por fonte.
      </ErrorState>
    )
  } else if (health.data.items.length === 0) {
    body = <EmptyState className="mt-3">Nenhuma fonte cadastrada.</EmptyState>
  } else {
    body = (
      <>
        <p className="mt-2 text-sm text-subtle">
          {health.data.items.length} fonte{health.data.items.length === 1 ? '' : 's'}
          {' · '}
          {health.data.failing === 0
            ? 'nenhuma com falha na última execução'
            : `${health.data.failing} com falha ou execução parcial`}
          .
        </p>
        <DataTable
          caption="Última execução de cada fonte"
          className="mt-3"
          columns={['Fonte', 'Última execução', 'Itens', 'Erro']}
          stickyFirstColumn
        >
          {health.data.items.map((source) => (
            <tr key={source.sourceDefinitionId}>
              <td>
                <PrimaryText>{source.name}</PrimaryText>
                <SecondaryText>
                  {source.sourceType} · {source.enabled ? 'habilitada' : 'desabilitada'}
                </SecondaryText>
              </td>
              <td>
                <StatusBadge
                  absent="Nunca executada"
                  labels={runStatusLabels}
                  tones={runStatusTones}
                  value={source.lastRunStatus}
                />
                <SecondaryText>{formatDate(source.lastRunFinishedAt)}</SecondaryText>
              </td>
              <td>{itemsText(source)}</td>
              <td className="text-subtle">
                {source.lastRunErrorCode ? (
                  `${source.lastRunErrorCode}: ${source.lastRunError ?? ''}`
                ) : (
                  <Unavailable reason="sem erro" />
                )}
              </td>
            </tr>
          ))}
        </DataTable>
      </>
    )
  }

  return (
    <section aria-labelledby="status-fontes-title" className="mt-6">
      <h2 className="text-section" id="status-fontes-title">
        Métricas por fonte
      </h2>
      {body}
    </section>
  )
}

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
      eyebrow="Estado do ambiente"
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

      <SourceMetrics />

      <section className="mt-6" aria-label="Como o estado é calculado">
        <h2 className="text-section">Como interpretar este estado</h2>
        <Card className="mt-3 p-4">
          <p className="text-sm text-subtle">
            A prontidão confirma que a API e a conexão com o banco de dados estão disponíveis.
            {state === 'ready'
              ? ' O ambiente está pronto para consultar o catálogo.'
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
