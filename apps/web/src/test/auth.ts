import { afterEach, beforeEach } from 'vitest'
import { setAuthSession, setAuthTokenGetter } from '../lib/api'

/** Installs a signed-in test identity and token getter for the current test file only. */
export function installTestAuth() {
  beforeEach(() => {
    setAuthSession('user_test', true)
    setAuthTokenGetter(async () => 'vitest-token')
  })
  afterEach(() => {
    setAuthTokenGetter(null)
    setAuthSession(null, false)
  })
}
