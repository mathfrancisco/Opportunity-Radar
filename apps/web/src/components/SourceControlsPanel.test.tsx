import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SourceControlsPanel } from './SourceControlsPanel'
import { render } from './testing'

afterEach(() => vi.unstubAllGlobals())

/** Flushes the micro- and macrotasks a react-query fetch resolves through. */
async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithClient(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

/** React tracks the input's previous value on the native element; a bare `.value =`
 * assignment does not fire the synthetic `onChange`, so tests must go through the
 * native setter before dispatching `input` (same pattern as InboxPage.test.tsx). */
function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  act(() => {
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

function sourceDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 'source-1',
    source_type: 'greenhouse',
    name: 'Fonte source-1',
    enabled: false,
    schedule: '0 0 * * *',
    priority: 100,
    configuration: { board_token: 'source-1' },
    evidence_status: 'unverified',
    reviewed_at: null,
    terms_reviewed: false,
    collector_local_tested: false,
    version: 1,
    ...overrides,
  }
}

/** Routes every request the panel makes, by method and path, never a real network call. */
function stubFetch(options: {
  detail?: Record<string, unknown>
  scheduleResponse?: { status: number; body: unknown }
}) {
  const calls: { method: string; url: string; body?: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, url, body })
      if (url.endsWith('/schedule')) {
        const response = options.scheduleResponse ?? {
          status: 200,
          body: sourceDetail({ schedule: body?.schedule ?? null, version: 2 }),
        }
        return new Response(JSON.stringify(response.body), { status: response.status })
      }
      if (/\/sources\/[^/?]+$/.test(url)) {
        return new Response(JSON.stringify(sourceDetail(options.detail)), { status: 200 })
      }
      return new Response('{}', { status: 200 })
    }),
  )
  return calls
}

describe('SourceControlsPanel — agenda', () => {
  it('mostra a agenda atual e envia o PATCH com a versão esperada', async () => {
    const calls = stubFetch({})
    const container = renderWithClient(<SourceControlsPanel sourceId="source-1" />)
    await flush()

    const input = container.querySelector<HTMLInputElement>('#schedule-source-1')
    expect(input?.value).toBe('0 0 * * *')

    typeInto(input!, '0 */3 * * *')
    await flush()

    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Salvar agenda',
    )
    expect(saveButton).toBeDefined()
    act(() => saveButton?.click())
    await flush()

    const scheduleCall = calls.find((call) => call.url.endsWith('/schedule'))
    expect(scheduleCall?.method).toBe('PATCH')
    expect(scheduleCall?.body).toEqual({ schedule: '0 */3 * * *', expected_version: 1 })
    expect(container.textContent).toContain('Agenda atualizada.')
  })

  it('agenda vazia envia null (fonte sem agenda)', async () => {
    const calls = stubFetch({})
    const container = renderWithClient(<SourceControlsPanel sourceId="source-1" />)
    await flush()

    const input = container.querySelector<HTMLInputElement>('#schedule-source-1')
    typeInto(input!, '')
    await flush()

    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Salvar agenda',
    )
    act(() => saveButton?.click())
    await flush()

    const scheduleCall = calls.find((call) => call.url.endsWith('/schedule'))
    expect(scheduleCall?.body).toEqual({ schedule: null, expected_version: 1 })
  })

  it('cron inválido (422) mostra o erro sem travar o formulário', async () => {
    stubFetch({
      scheduleResponse: {
        status: 422,
        body: { detail: { code: 'INVALID_CONFIGURATION', message: 'bad cron', field: 'schedule' } },
      },
    })
    const container = renderWithClient(<SourceControlsPanel sourceId="source-1" />)
    await flush()

    const input = container.querySelector<HTMLInputElement>('#schedule-source-1')
    typeInto(input!, 'not a cron')
    await flush()

    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Salvar agenda',
    )
    act(() => saveButton?.click())
    await flush()

    expect(container.textContent).toContain('bad cron')
  })

  it('conflito de versão (409) oferece recarregar', async () => {
    stubFetch({
      scheduleResponse: {
        status: 409,
        body: { detail: { code: 'version_conflict', message: 'stale' } },
      },
    })
    const container = renderWithClient(<SourceControlsPanel sourceId="source-1" />)
    await flush()

    const input = container.querySelector<HTMLInputElement>('#schedule-source-1')
    typeInto(input!, '0 */2 * * *')
    await flush()

    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Salvar agenda',
    )
    act(() => saveButton?.click())
    await flush()

    expect(container.textContent).toContain('A fonte mudou depois que você a abriu')
  })
})
