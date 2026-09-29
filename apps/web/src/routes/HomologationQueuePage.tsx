import { Link } from 'react-router-dom'
import { HomologationQueue } from '../components/HomologationQueue'
import { PageShell } from '../components/PageShell'
import { useActiveProfile } from '../features/profile/useProfile'

/**
 * The homologation queue (F20-25): every proposed source, one screen, instead of a
 * cartão-por-vez walk through the source list. Reached from a link on `SourcesPage`, not
 * from the primary nav — it is a working view over the same fontes, not a new section.
 */
export function HomologationQueuePage() {
  const profile = useActiveProfile()
  const hasInterestAreas =
    (profile.data?.preferences.targetRoleFamilies.length ?? 0) > 0

  return (
    <PageShell
      eyebrow="Aquisição"
      title="Fila de homologação"
      description="Teste, revise os termos e habilite as propostas em sequência, sem abrir fonte por fonte."
    >
      {!profile.isPending && !hasInterestAreas && (
        <p className="mt-4 rounded-2xl border border-warning-line bg-warning-surface p-4 text-sm text-warning-ink">
          O perfil ainda não tem áreas de interesse. Fontes habilitadas em massa só devem
          ir ao ar depois disso, para a Inbox conseguir filtrar por área.{' '}
          <Link className="underline decoration-2 underline-offset-4" to="/profile">
            Configurar o perfil
          </Link>
          .
        </p>
      )}
      <div className="mt-6">
        <HomologationQueue />
      </div>
    </PageShell>
  )
}
