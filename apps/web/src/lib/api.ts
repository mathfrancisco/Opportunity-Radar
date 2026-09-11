const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || '/api'
const apiBaseUrl = configuredBaseUrl.replace(/\/$/, '')

export function apiUrl(path: string) {
  return `${apiBaseUrl}${path}`
}
