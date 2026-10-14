import { act, type ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RequireOwnerUi } from './RouteGuards'

const clerkMock = vi.hoisted(() => ({
  isLoaded: true,
  isSignedIn: true,
  userId: 'owner' as string | null,
}))
const privateFetchMock = vi.hoisted(() => vi.fn())

vi.mock('@clerk/react', () => ({ useAuth: () => clerkMock }))
vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  privateFetch: privateFetchMock,
}))

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const roots: Root[] = []

function render(element: ReactElement) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return { container, root }
}

function guard(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RequireOwnerUi><p>owner content</p></RequireOwnerUi>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  return {
    promise: new Promise<Response>((done) => { resolve = done }),
    resolve,
  }
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

afterEach(() => {
  act(() => roots.splice(0).forEach((root) => root.unmount()))
  document.body.replaceChildren()
  clerkMock.isLoaded = true
  clerkMock.isSignedIn = true
  clerkMock.userId = 'owner'
  privateFetchMock.mockReset()
})

describe('RequireOwnerUi', () => {
  it('unlocks owner UI only for a true server capability', async () => {
    privateFetchMock.mockResolvedValue(new Response('{"is_owner":true}', { status: 200 }))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(guard(client))

    await settle()

    expect(client.getQueryData(['session', 'owner'])).toEqual({ is_owner: true })
    expect(container.textContent).toContain('owner content')
    expect(privateFetchMock).toHaveBeenCalledWith('/api/session')
  })

  it.each([
    ['non-owner', new Response('{"is_owner":false}', { status: 200 })],
    ['server error', new Response('{}', { status: 500 })],
    ['unauthorized', new Response('{}', { status: 401 })],
  ])('denies owner UI for $0', async (_, response) => {
    privateFetchMock.mockResolvedValue(response)
    const { container } = render(guard())

    await settle()

    expect(container.textContent).not.toContain('owner content')
  })

  it('denies owner UI while the session capability is pending', () => {
    privateFetchMock.mockReturnValue(new Promise(() => undefined))
    const { container } = render(guard())

    expect(container.textContent).not.toContain('owner content')
  })

  it('denies owner UI after logout', () => {
    clerkMock.isSignedIn = false
    clerkMock.userId = null
    const { container } = render(guard())

    expect(container.textContent).not.toContain('owner content')
    expect(privateFetchMock).not.toHaveBeenCalled()
  })

  it.each([
    { previous: true, next: false, label: 'a delayed owner response cannot unlock the next non-owner' },
    { previous: false, next: true, label: 'a delayed non-owner response cannot deny the next owner' },
  ])('$label', async ({ previous, next }) => {
    const oldRequest = deferredResponse()
    const newRequest = deferredResponse()
    privateFetchMock.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container, root } = render(guard(client))

    clerkMock.userId = 'new-user'
    act(() => root.render(guard(client)))
    oldRequest.resolve(new Response(JSON.stringify({ is_owner: previous }), { status: 200 }))
    await settle()

    expect(container.textContent).not.toContain('owner content')

    newRequest.resolve(new Response(JSON.stringify({ is_owner: next }), { status: 200 }))
    await settle()

    expect(container.textContent.includes('owner content')).toBe(next)
  })
})
