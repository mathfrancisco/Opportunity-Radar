const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || '/api'
const apiBaseUrl = configuredBaseUrl.replace(/\/$/, '')
type AuthTokenGetter = () => Promise<string | null>

let authTokenGetter: AuthTokenGetter | null = null
let authSession = { userId: null as string | null, isSignedIn: false, generation: 0 }

function requestMethod(input: RequestInfo | URL, init: RequestInit): string {
  if (init.method) return init.method.toUpperCase()
  return input instanceof Request ? input.method.toUpperCase() : 'GET'
}

function throwIfAborted(signal: AbortSignal | null | undefined) {
  if (!signal?.aborted) return
  throw signal.reason instanceof Error
    ? signal.reason
    : new DOMException('The operation was aborted.', 'AbortError')
}

/** A failed HTTP response whose method and status are safe for retry classification. */
export class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly method: string = 'GET',
  ) {
    super(message)
    this.name = 'HttpError'
  }
}

/** A browser transport failure, distinct from an invalid response body or parser error. */
export class NetworkError extends Error {
  constructor(message: string, readonly method: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

/** Supplies Clerk's current token getter to private API requests. */
export function setAuthTokenGetter(getToken: AuthTokenGetter | null) {
  authTokenGetter = getToken
}

/** Marks the current Clerk identity so stale token requests cannot cross sessions. */
export function setAuthSession(userId: string | null, isSignedIn: boolean) {
  if (authSession.userId !== userId || authSession.isSignedIn !== isSignedIn) {
    authSession = { userId, isSignedIn, generation: authSession.generation + 1 }
  }
}

/** Adds a fresh Clerk token to one private request without retaining it. */
export async function privateFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  if (authTokenGetter === null) throw new Error('A autenticação não está disponível.')
  throwIfAborted(init.signal)
  const sessionAtStart = authSession
  const token = await authTokenGetter()
  throwIfAborted(init.signal)
  if (!token) throw new Error('Entre na sua conta para acessar este recurso.')
  if (
    !sessionAtStart.isSignedIn ||
    !authSession.isSignedIn ||
    authSession.generation !== sessionAtStart.generation
  ) {
    throw new Error('Entre na sua conta para acessar este recurso.')
  }

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  try {
    return await fetch(input, { ...init, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    if (error instanceof TypeError) {
      throw new NetworkError(error.message || 'A rede não respondeu.', requestMethod(input, init))
    }
    throw error
  }
}

export function apiUrl(path: string) {
  return `${apiBaseUrl}${path}`
}

/**
 * A write that lost a race against another writer.
 *
 * Distinct from a failed request on purpose: a 409 means the record changed under the
 * operator, so the recovery is to read it again and decide, not to retry the same payload.
 * Retrying a conflict is how one of the two edits disappears silently.
 */
export class ConflictError extends HttpError {
  constructor(message: string, method = 'GET') {
    super(message, 409, method)
    this.name = 'ConflictError'
  }
}

/** Builds the error a failed response deserves, keeping the domain message when it sent one. */
export function requestFailure(status: number, message: string | null, method = 'GET'): HttpError {
  const detail = message ?? `A API respondeu com ${status}.`
  return status === 409 ? new ConflictError(detail, method) : new HttpError(detail, status, method)
}

/**
 * A refusal the server attributed to one field of the request.
 *
 * A form shows it under that field and keeps everything the operator typed; a refusal
 * with no field is shown once, above the actions. `field` is dotted for nested keys, as
 * the server sends it: `configuration.board_token`.
 */
export class FieldError extends HttpError {
  readonly field: string
  readonly code: string | null

  constructor(field: string, message: string, code: string | null = null, status = 422, method = 'GET') {
    super(message, status, method)
    this.name = 'FieldError'
    this.field = field
    this.code = code
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Reads a failed response into the error it deserves.
 *
 * Two shapes reach here: the domain's `{code, message, field?}` and FastAPI's own list of
 * validation errors, whose `loc` is `["body", "configuration", "board_token"]`. Both end up
 * as the same `FieldError`, so a form does not care which layer refused. A 409 is a
 * version conflict unless the server says it is about identity — a domain already owned
 * by another company is a fact about the request, not a race to re-read.
 */
export async function failureFrom(response: Response, method = 'GET'): Promise<Error> {
  const body: unknown = await response.json().catch(() => null)
  const detail = isRecord(body) ? body.detail : null
  if (Array.isArray(detail) && detail.length > 0 && isRecord(detail[0])) {
    const first = detail[0]
    const location = Array.isArray(first.loc)
      ? first.loc.filter((part) => part !== 'body').map(String)
      : []
    const message = typeof first.msg === 'string' ? first.msg : `A API respondeu com ${response.status}.`
    return location.length > 0
      ? new FieldError(location.join('.'), message, null, response.status, method)
      : new HttpError(message, response.status, method)
  }
  const code = isRecord(detail) && typeof detail.code === 'string' ? detail.code : null
  const message =
    isRecord(detail) && typeof detail.message === 'string'
      ? detail.message
      : typeof detail === 'string'
        ? detail
        : null
  const field = isRecord(detail) && typeof detail.field === 'string' ? detail.field : null
  if (field !== null) {
    return new FieldError(field, message ?? `A API respondeu com ${response.status}.`, code, response.status, method)
  }
  if (response.status === 409 && code === 'identity_conflict') {
    return new HttpError(message ?? 'A identidade já pertence a outro registro.', response.status, method)
  }
  return requestFailure(response.status, message, method)
}
