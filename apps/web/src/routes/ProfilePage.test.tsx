import { installTestAuth } from '../test/auth'
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
  it('mostra o contexto de decisão e marca Perfil na navegação', async () => {
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

    expect(container.textContent).toContain('Critérios de decisão')
    expect(
      container.querySelector('a[href="/profile"]')?.getAttribute('aria-current'),
    ).toBe('page')
    expect(container.querySelectorAll('nav [aria-current="page"]')).toHaveLength(1)

    const skillsLabel = [...container.querySelectorAll('label')].find(
      (label) => label.textContent?.includes('Skills'),
    )
    const skills = skillsLabel?.querySelector('input')
    expect(skills).not.toBeNull()
    expect(
      container.querySelector(`#${CSS.escape(skills!.getAttribute('aria-labelledby')!)}`)?.textContent,
    ).toBe('Skills')
    expect(
      container.querySelector(`#${CSS.escape(skills!.getAttribute('aria-describedby')!)}`)?.textContent,
    ).toBe('Separadas por vírgula.')
  })

  it('organizes the mounted form into reachable sections without losing a draft', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.endsWith('/profile/versions')) return new Response('[]')
        return new Response(JSON.stringify(version('version-1', 3, ['backend engineer'])))
      }),
    )

    const container = renderPage(<ProfilePage />)
    await flush()

    const navigation = [...container.querySelectorAll('nav')].find(
      (element) => element.getAttribute('aria-label') === 'Seções do perfil',
    )
    expect([...navigation!.querySelectorAll('a')].map((link) => link.getAttribute('href'))).toEqual([
      '#perfil-criterios',
      '#perfil-trabalho',
      '#perfil-remuneracao',
      '#profile-versions',
    ])
    expect(container.querySelector('#perfil-criterios-title')?.textContent).toBe('Skills e áreas')
    expect(container.querySelector('#perfil-trabalho-title')?.textContent).toBe('Trabalho e localização')
    expect(container.querySelector('#perfil-remuneracao-title')?.textContent).toBe('Remuneração')

    const titleField = [...container.querySelectorAll('label')].find((label) =>
      label.textContent?.includes('Cargos-alvo'),
    )
    const input = titleField?.querySelector('input')
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, 'Backend Engineer, Engenheiro de Software')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    })
    ;[...navigation!.querySelectorAll('a')]
      .find((link) => link.getAttribute('href') === '#perfil-remuneracao')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))

    expect(input?.value).toBe('Backend Engineer, Engenheiro de Software')
    expect(container.querySelector('#profile-versions-title')?.textContent).toBe('Versões')
  })

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

// R55-D4: "Não é para mim" feedback becomes a suggested adjustment, never an automatic one.
describe('ProfilePage — ajustes sugeridos pelo feedback', () => {
  const suggestionsBody = {
    min_marks: 2,
    suggestions: [
      { kind: 'REMOVE_SENIORITY', value: 'MID', marks: 3 },
      { kind: 'REMOVE_ROLE_FAMILY', value: 'DATA', marks: 2 },
      { kind: 'LOWER_COMPANY_PRIORITY', value: 'Acme Corp', marks: 2 },
    ],
  }

  function stubProfile(suggestions: unknown) {
    const fetchMock = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (init?.method === 'POST') return new Response(JSON.stringify(version('version-2', 4, [])))
      if (url.endsWith('/profile/suggestions')) {
        return new Response(JSON.stringify(suggestions))
      }
      if (url.endsWith('/profile/versions')) return new Response('[]')
      return new Response(
        JSON.stringify(
          version('version-1', 3, [], {
            targetRoleFamilies: ['SOFTWARE_ENGINEERING', 'DATA'],
          }),
        ),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  it('mostra cada sugestão com o motivo e a contagem de marcas', async () => {
    stubProfile(suggestionsBody)

    const container = renderPage(<ProfilePage />)
    await flush(6)

    const section = container.querySelector('#ajustes-sugeridos') as HTMLElement
    expect(section.querySelector('h2')?.textContent).toBe('Ajustes sugeridos pelo seu feedback')
    expect(section.textContent).toContain('Nada muda sozinho')
    expect(section.textContent).toContain('Remover "Pleno" das senioridades aceitas.')
    expect(section.textContent).toContain('3 vagas do nível Pleno marcadas')
    expect(section.textContent).toContain('Remover "Dados" das áreas de interesse.')
    expect(section.textContent).toContain('Reduzir a prioridade da empresa Acme Corp.')
    expect(section.querySelector('a[href="/companies"]')).not.toBeNull()
  })

  it('não mostra a seção quando não há sugestão', async () => {
    stubProfile({ min_marks: 2, suggestions: [] })

    const container = renderPage(<ProfilePage />)
    await flush(6)

    expect(container.querySelector('#ajustes-sugeridos')).toBeNull()
    expect(container.querySelector('form')).not.toBeNull()
  })

  it('aplicar altera só o rascunho do formulário e nunca grava uma versão', async () => {
    const fetchMock = stubProfile(suggestionsBody)

    const container = renderPage(<ProfilePage />)
    await flush(6)

    const boxes = () => [
      ...container.querySelectorAll<HTMLInputElement>('form fieldset input[type="checkbox"]'),
    ]
    const box = (label: string) =>
      boxes().find((input) => input.closest('label')?.textContent?.includes(label))
    expect(box('Pleno')?.checked).toBe(true)
    expect(box('Dados')?.checked).toBe(true)

    const apply = [...container.querySelectorAll('#ajustes-sugeridos button')].find((button) =>
      button.closest('li')?.textContent?.includes('Pleno'),
    ) as HTMLButtonElement
    expect(apply.textContent).toBe('Aplicar ao rascunho')
    await act(async () => {
      apply.click()
    })

    expect(box('Pleno')?.checked).toBe(false)
    expect(box('Dados')?.checked).toBe(true)
    expect(apply.textContent).toBe('Aplicado ao rascunho')
    expect(apply.disabled).toBe(true)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
  })

  it('salvar depois de aplicar envia a preferência ajustada como nova versão', async () => {
    const fetchMock = stubProfile(suggestionsBody)

    const container = renderPage(<ProfilePage />)
    await flush(6)

    const apply = [...container.querySelectorAll('#ajustes-sugeridos button')].find((button) =>
      button.closest('li')?.textContent?.includes('Dados'),
    ) as HTMLButtonElement
    await act(async () => {
      apply.click()
    })
    await act(async () => {
      container
        .querySelector('form')
        ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await flush()

    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts).toHaveLength(1)
    const body = JSON.parse(String(posts[0][1]?.body)) as {
      preferences: { target_role_families: string[] }
    }
    expect(body.preferences.target_role_families).toEqual(['SOFTWARE_ENGINEERING'])
  })

  it('uma falha ao ler as sugestões não impede editar o perfil', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.endsWith('/profile/suggestions')) return new Response('{}', { status: 500 })
        if (url.endsWith('/profile/versions')) return new Response('[]')
        return new Response(JSON.stringify(version('version-1', 3, [])))
      }),
    )

    const container = renderPage(<ProfilePage />)
    await flush(6)

    expect(container.querySelector('#ajustes-sugeridos')).toBeNull()
    expect(container.querySelector('form')).not.toBeNull()
  })
})

installTestAuth()
