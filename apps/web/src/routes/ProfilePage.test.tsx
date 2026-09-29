import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { ProfilePage } from './ProfilePage'

afterEach(() => vi.unstubAllGlobals())

function version(
  id: string,
  lock: number,
  targetTitles: string[],
  extra: {
    skills?: object[]
    targetRoleFamilies?: string[]
    acceptedSeniorities?: string[]
  } = {},
) {
  return {
    id,
    number: lock,
    status: 'ACTIVE',
    profile_lock_version: lock,
    skills: extra.skills ?? [],
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
      target_role_families: extra.targetRoleFamilies ?? [],
      target_titles: targetTitles,
      accepted_seniorities: extra.acceptedSeniorities ?? ['INTERN', 'JUNIOR', 'MID', 'UNKNOWN'],
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

  it('warns that the Inbox does not filter by area when areas or skills are empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.endsWith('/profile/versions')) return new Response('[]')
        return new Response(JSON.stringify(version('version-1', 3, [])))
      }),
    )

    const container = renderPage(<ProfilePage />)
    await flush()

    const alert = container.querySelector('[role="status"]')
    expect(alert?.textContent).toContain('o Inbox não filtra por área')
    expect(alert?.textContent).toContain('skill')
  })

  it('shows no warning when areas and skills are filled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.endsWith('/profile/versions')) return new Response('[]')
        return new Response(
          JSON.stringify(
            version('version-1', 3, [], {
              skills: [{ canonical_name: 'python' }],
              targetRoleFamilies: ['DATA'],
            }),
          ),
        )
      }),
    )

    const container = renderPage(<ProfilePage />)
    await flush()

    expect(container.querySelector('[role="status"]')).toBeNull()
  })

  it('edits and saves the accepted seniorities', async () => {
    const fetchMock = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/profile/versions') && init?.method === 'POST') {
        return new Response(JSON.stringify(version('version-2', 4, [])), { status: 201 })
      }
      if (url.endsWith('/profile/versions')) return new Response('[]')
      return new Response(JSON.stringify(version('version-1', 3, [])))
    })
    vi.stubGlobal('fetch', fetchMock)

    const container = renderPage(<ProfilePage />)
    await flush()

    const boxes = [
      ...container.querySelectorAll<HTMLInputElement>('fieldset input[type="checkbox"]'),
    ]
    const box = (label: string) =>
      boxes.find((input) => input.closest('label')?.textContent?.includes(label))
    expect(box('Júnior')?.checked).toBe(true)
    expect(box('Sênior')?.checked).toBe(false)

    await act(async () => {
      box('Sênior')?.click()
    })
    await act(async () => {
      container.querySelector('form')?.dispatchEvent(
        new Event('submit', { bubbles: true, cancelable: true }),
      )
    })
    await flush()

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    const body = JSON.parse(String(post?.[1]?.body)) as {
      preferences: { accepted_seniorities: string[] }
    }
    expect(body.preferences.accepted_seniorities).toEqual([
      'INTERN',
      'JUNIOR',
      'MID',
      'UNKNOWN',
      'SENIOR',
    ])
  })
})
