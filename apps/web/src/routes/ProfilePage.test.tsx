import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { ProfilePage } from './ProfilePage'

afterEach(() => vi.unstubAllGlobals())

function version(id: string, lock: number, targetTitles: string[]) {
  return {
    id,
    number: lock,
    status: 'ACTIVE',
    profile_lock_version: lock,
    skills: [],
    experiences: [],
    projects: [],
    preferences: {
      work_modes: [],
      contracts: [],
      countries: [],
      timezone_start_hour: null,
      timezone_end_hour: null,
      compensation_min: null,
      compensation_max: null,
      compensation_currency: null,
      compensation_period: null,
      relocation_allowed: false,
      sponsorship_required: false,
      target_role_families: [],
      target_titles: targetTitles,
    },
  }
}

function renderPage(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

describe('ProfilePage', () => {
  it('shows and saves target titles', async () => {
    const fetchMock = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/profile') && !url.endsWith('/profile/versions')) {
        return new Response(JSON.stringify(version('version-1', 3, ['backend engineer'])))
      }
      if (url.endsWith('/profile/versions') && (!init || init.method === undefined)) {
        return new Response('[]')
      }
      if (url.endsWith('/profile/versions') && init?.method === 'POST') {
        const request = JSON.parse(String(init.body)) as {
          preferences: { target_titles: string[] }
        }
        return new Response(
          JSON.stringify(version('version-2', 4, request.preferences.target_titles)),
          { status: 201 },
        )
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const container = renderPage(<ProfilePage />)
    await flush()

    const titleField = [...container.querySelectorAll('label')].find((label) =>
      label.textContent?.includes('Cargos-alvo'),
    )
    const input = titleField?.querySelector('input')
    expect(input?.value).toBe('backend engineer')

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, 'Backend Engineer, Engenheiro de Software')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      container.querySelector('form')?.dispatchEvent(
        new Event('submit', { bubbles: true, cancelable: true }),
      )
    })
    await flush()

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(post).toBeDefined()
    const body = JSON.parse(String(post?.[1]?.body)) as {
      preferences: { target_titles: string[] }
    }
    expect(body.preferences.target_titles).toEqual([
      'Backend Engineer',
      'Engenheiro de Software',
    ])
  })
})
