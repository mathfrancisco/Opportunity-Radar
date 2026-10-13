import { beforeEach } from 'vitest'
import { setAuthTokenGetter } from './lib/api'

beforeEach(() => {
  setAuthTokenGetter(async () => 'vitest-token')
})
