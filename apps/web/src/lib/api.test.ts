import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ConflictError,
  FieldError,
  NetworkError,
  failureFrom,
  privateFetch,
  requestFailure,
  setAuthSession,
  setAuthTokenGetter,
} from './api'

afterEach(() => {
  setAuthTokenGetter(null)
  setAuthSession(null, false)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('requestFailure', () => {
  it('marca 409 como conflito, porque repetir a escrita apagaria a outra edição', () => {
    const error = requestFailure(409, 'A candidatura mudou.')

    expect(error).toBeInstanceOf(ConflictError)
    expect(error.message).toBe('A candidatura mudou.')
  })

  it('mantém erro comum para as demais falhas', () => {
    const error = requestFailure(503, null)

    expect(error).not.toBeInstanceOf(ConflictError)
    expect(error.message).toBe('A API respondeu com 503.')
  })

  it('prefere a mensagem do domínio à do status', () => {
    expect(requestFailure(422, 'Fonte externa exige termos revisados.').message).toBe(
      'Fonte externa exige termos revisados.',
    )
  })
})

function reply(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status })
}

describe('failureFrom', () => {
  it('leva a recusa do domínio ao campo que a causou', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'INVALID_CONFIGURATION',
            message: 'Greenhouse company_reference must be a non-empty board token',
            field: 'configuration.board_token',
          },
        },
        422,
      ),
    )

    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('configuration.board_token')
    expect(error.message).toContain('board token')
  })

  it('lê a validação do FastAPI pelo mesmo caminho, sem o prefixo body', async () => {
    const error = await failureFrom(
      reply(
        { detail: [{ loc: ['body', 'name'], msg: 'String should have at least 1 character' }] },
        422,
      ),
    )

    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('name')
  })

  it('trata versão desatualizada como conflito, para reler e não reenviar', async () => {
    const error = await failureFrom(
      reply({ detail: { code: 'version_conflict', message: 'source definition was changed' } }, 409),
    )

    expect(error).toBeInstanceOf(ConflictError)
  })

  it('não confunde conflito de identidade com corrida de versão', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'identity_conflict',
            message: 'domain acme.com already belongs to Acme',
            field: 'domain',
          },
        },
        409,
      ),
    )

    expect(error).not.toBeInstanceOf(ConflictError)
    expect(error).toBeInstanceOf(FieldError)
    expect((error as FieldError).field).toBe('domain')
  })

  it('mantém a mensagem do domínio quando não há campo', async () => {
    const error = await failureFrom(
      reply(
        {
          detail: {
            code: 'INVALID_CONFIGURATION',
            message: 'external sources require confirmed evidence',
          },
        },
        422,
      ),
    )

    expect(error).not.toBeInstanceOf(FieldError)
    expect(error.message).toBe('external sources require confirmed evidence')
  })
})

describe('privateFetch', () => {
  it('gets a fresh token for every request without persisting it', async () => {
    const order: string[] = []
    const tokens = ['test-token-one', 'test-token-two']
    const getToken = vi.fn(async () => {
      order.push('token')
      return tokens.shift() ?? null
    })
    const fetchMock = vi.fn<typeof fetch>(async () => {
      order.push('request')
      return new Response('{}', { status: 200 })
    })
    const serialize = vi.spyOn(JSON, 'stringify')
    const log = vi.spyOn(console, 'log')
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(getToken)
    setAuthSession('user-a', true)

    await privateFetch('/private/one')
    await privateFetch('/private/two')

    expect(getToken).toHaveBeenCalledTimes(2)
    expect(order).toEqual(['token', 'request', 'token', 'request'])
    expect(fetchMock.mock.calls.map(([input, init]) => [input, new Headers(init?.headers).get('Authorization')])).toEqual([
      ['/private/one', 'Bearer test-token-one'],
      ['/private/two', 'Bearer test-token-two'],
    ])
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(serialize).not.toHaveBeenCalled()
    expect(log).not.toHaveBeenCalled()
  })

  it.each([null, ''])('does not send a private request when Clerk returns no token (%s)', async (token) => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(async () => token)
    setAuthSession('user-a', true)

    await expect(privateFetch('/private/one')).rejects.toThrow('Entre na sua conta')

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not send a resolved token after auth identity changes', async () => {
    let resolveToken: (token: string) => void = () => undefined
    const tokenPromise = new Promise<string>((resolve) => {
      resolveToken = resolve
    })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(() => tokenPromise)
    setAuthSession('user-a', true)

    const request = privateFetch('/private/stale')
    setAuthSession('user-b', true)
    resolveToken('stale-token')

    await expect(request).rejects.toThrow('Entre na sua conta')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not ask Clerk or the network for an already aborted request', async () => {
    const getToken = vi.fn(async () => 'test-token')
    const fetchMock = vi.fn()
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(getToken)
    setAuthSession('user-a', true)

    await expect(privateFetch('/private/aborted', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(getToken).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('stops after a token resolves if the query was cancelled', async () => {
    let resolveToken: (token: string) => void = () => undefined
    const token = new Promise<string>((resolve) => { resolveToken = resolve })
    const getToken = vi.fn(() => token)
    const fetchMock = vi.fn()
    const controller = new AbortController()
    vi.stubGlobal('fetch', fetchMock)
    setAuthTokenGetter(getToken)
    setAuthSession('user-a', true)

    const request = privateFetch('/private/cancelled-after-token', { signal: controller.signal })
    controller.abort()
    resolveToken('test-token')

    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('labels browser transport TypeError separately from response parsing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    setAuthTokenGetter(async () => 'test-token')
    setAuthSession('user-a', true)

    await expect(privateFetch('/private/offline')).rejects.toBeInstanceOf(NetworkError)
  })
})
