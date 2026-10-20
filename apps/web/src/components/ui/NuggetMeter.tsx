interface NuggetMeterProps {
  met: number
  missed?: number
  unknown?: number
  label: string
}

const nuggetShape: Record<'met' | 'missed' | 'unknown', string> = {
  met: 'border-nugget bg-nugget',
  missed: 'border-nugget bg-transparent',
  unknown: 'border-dashed border-muted bg-transparent',
}

const count = (n: number): number => (Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0)

/** Nuggets in the order met, missed, unknown; the label is always shown beside them (hidden from AT: role=img already announces it). */
export function NuggetMeter({ met, missed = 0, unknown = 0, label }: NuggetMeterProps) {
  const nuggets = [
    ...Array<'met'>(count(met)).fill('met'),
    ...Array<'missed'>(count(missed)).fill('missed'),
    ...Array<'unknown'>(count(unknown)).fill('unknown'),
  ]
  return (
    <span className="inline-flex items-center gap-2">
      <span role="img" aria-label={label} className="inline-flex items-center gap-1">
        {nuggets.map((kind, index) => (
          <span
            key={index}
            data-nugget={kind}
            className={`h-2.5 w-2.5 rounded-full border ${nuggetShape[kind]}`}
          />
        ))}
      </span>
      <span aria-hidden="true" className="text-caption text-subtle">{label}</span>
    </span>
  )
}
