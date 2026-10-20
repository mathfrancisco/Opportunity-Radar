import { useState } from 'react'
import {
  applyThemePreference,
  readThemePreference,
  writeThemePreference,
  type ThemePreference,
} from '../../lib/theme'

const options: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Sistema' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
]

export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(readThemePreference)

  function choose(next: ThemePreference) {
    writeThemePreference(next)
    applyThemePreference(next)
    setPreference(next)
  }

  return (
    <div role="group" aria-label="Tema" className="flex rounded-control border border-line-strong p-0.5">
      {options.map((option) => {
        const pressed = option.value === preference
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={pressed}
            onClick={() => choose(option.value)}
            className={`flex-1 rounded-control border px-2 text-caption max-md:min-h-11 md:h-7 ${
              pressed
                ? 'border-control-line bg-surface font-semibold text-ink'
                : 'border-transparent text-subtle hover:text-ink'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
