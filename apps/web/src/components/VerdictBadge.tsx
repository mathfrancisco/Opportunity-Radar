import { verdictLabels, verdictTones } from '../features/matching/verdicts'
import { StatusBadge } from './StatusBadge'

/** The deterministic verdict as a chip. A verdict with no label reads as unrecognised, never as its code. */
export function VerdictBadge({ verdict }: { verdict: string | null }) {
  const labels =
    verdict === null || verdict in verdictLabels
      ? verdictLabels
      : { [verdict]: 'Estado não reconhecido' }
  return <StatusBadge absent="Não avaliada" labels={labels} tones={verdictTones} value={verdict} />
}
