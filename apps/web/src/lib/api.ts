const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || '/api'
const apiBaseUrl = configuredBaseUrl.replace(/\/$/, '')

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
export class ConflictError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ConflictError'
  }
}

/** Builds the error a failed response deserves, keeping the domain message when it sent one. */
export function requestFailure(status: number, message: string | null): Error {
  const detail = message ?? `A API respondeu com ${status}.`
  return status === 409 ? new ConflictError(detail) : new Error(detail)
}

/**
 * A refusal the server attributed to one field of the request.
 *
 * A form shows it under that field and keeps everything the operator typed; a refusal
 * with no field is shown once, above the actions. `field` is dotted for nested keys, as
 * the server sends it: `configuration.board_token`.
 */
export class FieldError extends Error {
  readonly field: string
  readonly code: string | null

  constructor(field: string, message: string, code: string | null = null) {
    super(message)
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
export async function failureFrom(response: Response): Promise<Error> {
  const body: unknown = await response.json().catch(() => null)
  const detail = isRecord(body) ? body.detail : null
  if (Array.isArray(detail) && detail.length > 0 && isRecord(detail[0])) {
    const first = detail[0]
    const location = Array.isArray(first.loc)
      ? first.loc.filter((part) => part !== 'body').map(String)
      : []
    const message = typeof first.msg === 'string' ? first.msg : `A API respondeu com ${response.status}.`
    return location.length > 0 ? new FieldError(location.join('.'), message) : new Error(message)
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
    return new FieldError(field, message ?? `A API respondeu com ${response.status}.`, code)
  }
  if (response.status === 409 && code === 'identity_conflict') {
    return new Error(message ?? 'A identidade já pertence a outro registro.')
  }
  return requestFailure(response.status, message)
}
