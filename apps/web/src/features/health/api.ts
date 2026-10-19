import { apiUrl, failureFrom, privateFetch } from '../../lib/api'

export type ServiceHealth = 'ready' | 'degraded'

export interface Readiness {
  state: ServiceHealth
  detail?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export async function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  const response = await privateFetch(apiUrl('/health/ready'), {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw await failureFrom(response)
  }

  const body: unknown = await response.json()
  if (!isRecord(body)) {
    throw new Error('A API retornou uma resposta de saúde inválida.')
  }

  if (body.status !== 'ready') {
    throw new Error('A API ainda não está pronta.')
  }

  const healthResponse = await privateFetch(apiUrl('/health'), {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!healthResponse.ok) {
    throw await failureFrom(healthResponse)
  }

  const health: unknown = await healthResponse.json()
  const ai = isRecord(health) && isRecord(health.ai) ? health.ai : undefined
  const aiStatus = typeof ai?.status === 'string' ? ai.status.toLowerCase() : 'unknown'
  const state: ServiceHealth = aiStatus === 'healthy' ? 'ready' : 'degraded'
  const detail = state === 'degraded' ? 'IA indisponível. A coleta e as regras continuam disponíveis.' : undefined

  return { state, detail }
}
