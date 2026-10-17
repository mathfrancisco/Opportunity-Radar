/** R55-D6: a source configuration value as one line of readable text. */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Primitive values and lists of them as one line; `null` as an em dash. */
export function configText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'sim' : 'não'
  if (Array.isArray(value)) return value.length === 0 ? '—' : value.map(configText).join(', ')
  if (isRecord(value)) return Object.entries(value).map(([k, v]) => `${k}: ${configText(v)}`).join('; ')
  return String(value)
}

