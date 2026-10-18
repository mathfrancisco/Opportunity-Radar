/** R55-D6: a source configuration value as readable text, never `[object Object]`. */

import { configText, isRecord } from './configText'

const MAX_DEPTH = 4

/**
 * Nested records (the `homologation_audit` evidence) become a nested definition list, one
 * key per line; everything else is a single line of text.
 */
export function ConfigValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (!isRecord(value) || depth >= MAX_DEPTH) return <>{configText(value)}</>
  const entries = Object.entries(value)
  if (entries.length === 0) return <>—</>
  return (
    <dl className="grid gap-1 border-l border-line pl-3 font-normal">
      {entries.map(([key, entry]) => (
        <div className="flex flex-wrap gap-x-2" key={key}>
          <dt className="text-muted">{key}</dt>
          <dd className="break-anywhere font-medium">
            <ConfigValue depth={depth + 1} value={entry} />
          </dd>
        </div>
      ))}
    </dl>
  )
}
