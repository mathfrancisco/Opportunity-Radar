export type ThemePreference = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'bateia-theme'
const CHANGE_EVENT = 'bateia-theme-change'

// Fallback for blocked storage: the choice still holds for this page view.
let memoryPreference: ThemePreference | null = null

export function readThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    // Fall through to the in-memory choice.
  }
  return memoryPreference ?? 'system'
}

export function writeThemePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, preference)
    memoryPreference = null
  } catch {
    memoryPreference = preference
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function subscribeThemePreference(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener)
  return () => window.removeEventListener(CHANGE_EVENT, listener)
}

function syncThemeColorMetas(preference: ThemePreference, doc: Document): void {
  const metas = [...doc.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')]
  for (const meta of metas) {
    if (!meta.dataset.default) meta.dataset.default = meta.content
  }
  const source =
    preference === 'system'
      ? null
      : metas.find((m) => m.getAttribute('media')?.includes(`prefers-color-scheme: ${preference}`))
  for (const meta of metas) meta.content = source ? source.dataset.default! : meta.dataset.default!
}

export function applyThemePreference(
  preference: ThemePreference,
  root: HTMLElement = document.documentElement,
): void {
  if (preference === 'system') root.removeAttribute('data-theme')
  else root.dataset.theme = preference
  syncThemeColorMetas(preference, root.ownerDocument)
}
