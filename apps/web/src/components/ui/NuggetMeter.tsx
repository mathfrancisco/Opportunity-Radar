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

/** Nuggets in the order met, missed, unknown; the label is always shown beside them. */
export function NuggetMeter({ met, missed = 0, unknown = 0, label }: NuggetMeterProps) {
  const nuggets = [
    ...Array<'met'>(Math.max(0, met)).fill('met'),
    ...Array<'missed'>(Math.max(0, missed)).fill('missed'),
    ...Array<'unknown'>(Math.max(0, unknown)).fill('unknown'),
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
      <span className="text-caption text-subtle">{label}</span>
    </span>
  )
}
