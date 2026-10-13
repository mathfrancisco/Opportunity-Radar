import { Show, UserButton } from '@clerk/react'

export function AuthenticationControls() {
  return (
    <div aria-label="Autenticação" className="fixed right-4 top-4 z-20 flex items-center gap-2">
      <Show when="signed-in">
        <UserButton />
      </Show>
    </div>
  )
}
