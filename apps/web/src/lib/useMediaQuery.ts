import { useEffect, useState } from 'react'

/**
 * Tracks a CSS media query. Where `matchMedia` does not exist (jsdom) the answer is
 * `fallback`, so a test renders the desktop layout unless it stubs the query.
 */
export function useMediaQuery(query: string, fallback = true): boolean {
  const read = () =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : fallback
  const [matches, setMatches] = useState(read)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(query)
    const onChange = () => setMatches(list.matches)
    onChange()
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])
  return matches
}
