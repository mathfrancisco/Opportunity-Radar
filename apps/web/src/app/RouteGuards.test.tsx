import { act, type ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
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
      <MemoryRouter initialEntries={['/owner']}>
        <RequireOwnerUi><p>owner content</p></RequireOwnerUi>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
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
    await new Promise((resolve) => setTimeout(resolve, 0))
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
  it('holds the owner route while pending, then unlocks it for a true server capability', async () => {
    const request = deferredResponse()
    privateFetchMock.mockReturnValue(request.promise)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(guard(client))

    expect(container.querySelector('[role="status"]')).not.toBeNull()
    expect(container.textContent).not.toContain('owner content')
    expect(container.querySelector('[data-testid="location"]')?.textContent).toBe('/owner')

    await settle()
    request.resolve(new Response('{"is_owner":true}', { status: 200 }))
    await settle()

    expect(client.getQueryData(['session', 'owner'])).toEqual({ is_owner: true })
    expect(container.textContent).toContain('owner content')
    expect(container.querySelector('[data-testid="location"]')?.textContent).toBe('/owner')
    expect(privateFetchMock).toHaveBeenCalledWith('/api/session', expect.objectContaining({
      signal: expect.any(AbortSignal),
    }))
  })

  it.each([
    ['non-owner', new Response('{"is_owner":false}', { status: 200 })],
    ['server error', new Response('{}', { status: 500 })],
    ['unauthorized', new Response('{}', { status: 401 })],
  ])('denies owner UI and redirects for $0', async (_, response) => {
    privateFetchMock.mockResolvedValue(response)
    const { container } = render(guard())

    await settle()

    expect(container.textContent).not.toContain('owner content')
    expect(container.querySelector('[data-testid="location"]')?.textContent).toBe('/')
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
