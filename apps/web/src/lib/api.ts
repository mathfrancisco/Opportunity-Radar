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
