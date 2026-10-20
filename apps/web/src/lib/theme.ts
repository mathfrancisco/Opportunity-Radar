export type ThemePreference = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'bateia-theme'

export function readThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function writeThemePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, preference)
  } catch {
    // Storage can be blocked; the choice still applies for this page view.
  }
}

export function applyThemePreference(
  preference: ThemePreference,
  root: HTMLElement = document.documentElement,
): void {
  if (preference === 'system') root.removeAttribute('data-theme')
  else root.dataset.theme = preference
}
