# CARD F20-59 — Landing.jobs como fonte de vagas

- **Status:** Fechado — não viável. Revisão em
  [`docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`](../../pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md)
  (2026-09-28): os Termos de Uso vigentes da Landing.jobs (`landing.jobs/tos`, atualizados
  2026-04-17), Seção 8, proíbem nomeadamente "use... scripts, robots... to access, monitor,
  scrape or copy the Platform" e "distribute any information obtained from the Platform", sem
  nenhuma cláusula própria de API/parceria que abra excepção — a "Plataforma" é definida como
  o site, onde a API também vive. A API pública documentada
  (`github.com/LandingJobs/LandingJobs-api`) foi confirmada **ainda ativa** (`GET
  /api/v1/jobs` e `/api/v1/companies` retornaram `200` com dados reais, sem autenticação), mas
  isso não supera o Termo — mesma lógica do F20-51 (GraphQL da Wellfound tecnicamente
  alcançável, decisão pelo Termo). Nenhum código foi escrito.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de landing.jobs/jobs; Landing.jobs teve API pública —
  verificar status atual"), tratado com a mesma régua do F20-32/F20-51/F20-52.

## Contexto

Landing.jobs é um board de vaga tech focado em Europa/Portugal, com uma API HTTP pública
documentada no GitHub oficial da empresa desde antes desta fase. O pedido do usuário pedia
explicitamente para confirmar se essa API ainda está ativa e sob quais termos — confirmado:
está ativa, mas os Termos gerais do site não a isentam da proibição de scraping/redistribuição.

## Escopo

1. **Revisão de termos e da API** registrada em `docs/pesquisas/` antes de qualquer código:
   `robots.txt`, Termos de Uso vigentes (buscar especificamente por cláusula própria de
   API/parceria, não só a cláusula geral de scraping), status atual do endpoint documentado
   (`api/v1/jobs`, `api/v1/companies`: ainda responde? exige autenticação hoje?), autenticação
   e anti-bot. Termo com proibição nomeada de scraping/cópia/distribuição de conteúdo da
   Plataforma, sem cláusula de API que a isente, encerra o card mesmo com o endpoint
   tecnicamente aberto.
2. Se viável: coletor consumindo o endpoint documentado, com a interface dos atuais
   (`source_type`, `CollectorCapabilities`, `discover`, telemetria, política de rede,
   retentativa, validador de chave).
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Contato comercial com a Landing.jobs para negociar um acordo de API/parceria — fora do
  mandato desta revisão (só leitura pública).
- Raspagem de HTML/DOM da Landing.jobs (o endpoint JSON, quando usado nesta revisão só para
  verificar status, já é estruturado — mas os Termos o proíbem, ver "Resultado").

## Resultado da revisão

**Não viável, apesar do endpoint técnico ainda estar aberto.** Ver a pesquisa citada para o
texto completo. Resumo:

- `robots.txt` bloqueia nomeadamente `/api/` e `/jobs/search` (não bloqueia `/jobs` isolado) —
  sinal técnico relevante, mas não decide por si (mesma regra do F20-32).
- Termos de Uso, Seção 8 ("Prohibited Uses"), três cláusulas relevantes: "access, monitor,
  scrape or copy the Platform" via "software, devices, scripts, robots"; "distribute any
  information obtained from the Platform"; "[monetizing] the platform without permission".
  Busca por "API" no documento inteiro não encontrou nenhuma menção — sem cláusula própria
  que isente o endpoint documentado.
- API confirmada ativa nesta revisão: `GET /api/v1/jobs` e `/api/v1/companies` responderam
  `200` com dados reais de vaga, sem autenticação. Documentada em
  `github.com/LandingJobs/LandingJobs-api`, sem termo de uso próprio, sem licença, sem aviso
  de descontinuação no README.
- Landing.jobs é board próprio — a integração com Greenhouse/Workable citada publicamente é
  para exportar candidatura da empresa, não para hospedar a vaga num ATS que o radar coleta.

## Critérios de aceite

- [x] Termos e status atual da API revisados e registrados antes do código —
      `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`, decisão: não
      viável. Os critérios seguintes não se aplicam.
- [ ] Coletor consumindo a API, com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma vaga real coletada via Landing.jobs. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma coleta em lote foi feita; as únicas requisições desta
  revisão foram `robots.txt`, a página pública de Termos, e duas chamadas `GET` simples
  (`/api/v1/jobs`, `/api/v1/companies`) só para confirmar que o endpoint documentado ainda
  responde hoje — listadas na pesquisa citada.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar (compartilhado com F20-56/57/58) | `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md` | Revisão de termos, robots.txt, API e anti-bot dos quatro sites, feita em conjunto. Entregável final deste card: decisão "não viável" para Landing.jobs. |

## Não fazer

- Não implementar coletor para a API da Landing.jobs sem um acordo de parceria explícito.
- Não fazer coleta em lote ou paginação exaustiva contra o endpoint documentado.
- Não contornar o `Disallow: /api/` do `robots.txt`.

## Pronto quando

A revisão está registrada com decisão e evidência (incluindo o status atual confirmado da
API), e o card está marcado como fechado — não viável, sem código pendente. Se o usuário
decidir buscar um acordo comercial com a Landing.jobs, isso abre um card novo, fora desta
revisão.
