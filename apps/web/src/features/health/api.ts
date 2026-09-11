import { apiUrl } from '../../lib/api'

export type ServiceHealth = 'ready' | 'degraded'

export interface Readiness {
  state: ServiceHealth
  detail?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export async function getReadiness(): Promise<Readiness> {
  const response = await fetch(apiUrl('/health/ready'), {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`A API respondeu com ${response.status}.`)
  }

  const body: unknown = await response.json()
  if (!isRecord(body)) {
    throw new Error('A API retornou uma resposta de saúde inválida.')
  }

  if (body.status !== 'ready') {
    throw new Error('A API ainda não está pronta.')
  }

  const healthResponse = await fetch(apiUrl('/health'), {
    headers: { Accept: 'application/json' },
  })

  if (!healthResponse.ok) {
    throw new Error(`A API respondeu com ${healthResponse.status}.`)
  }

  const health: unknown = await healthResponse.json()
  const ollama = isRecord(health) && isRecord(health.ollama) ? health.ollama : undefined
  const ollamaStatus = typeof ollama?.status === 'string' ? ollama.status.toLowerCase() : 'unknown'
  const state: ServiceHealth = ollamaStatus === 'healthy' ? 'ready' : 'degraded'
  const detail = state === 'degraded' ? 'Ollama indisponível. A coleta e as regras continuam disponíveis.' : undefined

  return { state, detail }
}
