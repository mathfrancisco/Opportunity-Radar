# CARD F20-56 — Braintrust como fonte de vagas

- **Status:** Fechado — não viável. Revisão em
  [`docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`](../../pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md)
  (2026-09-28): não há cláusula nomeada de Termos que bloqueie (Braintrust/Talent Node só
  proíbe "ferramenta não autorizada" e engenharia reversa, cláusula genérica), mas também não
  existe endpoint estruturado — a página `/jobs/` é uma SPA React sem `JobPosting` em
  `schema.org` no HTML inicial e sem API pública documentada. Nenhum código foi escrito:
  nenhum arquivo em `src/opportunity_radar/acquisition/` foi criado ou alterado.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de app.usebraintrust.com/jobs/"), tratado com a mesma régua
  do F20-32/F20-51/F20-52.

## Contexto

Braintrust (`app.usebraintrust.com/jobs/`) é uma marketplace de talentos com aplicação e
bidding na própria plataforma (sem redirecionar para ATS de empresa cliente). Foi avaliada
como fonte direta de vaga.

## Escopo

1. **Revisão de termos e de endpoint** registrada em `docs/pesquisas/` antes de qualquer
   código: `robots.txt`, Termos de Uso, API pública, autenticação, anti-bot, e se o HTML
   inicial expõe `schema.org`/`JobPosting`. Ausência de cláusula bloqueante **e** ausência de
   endpoint estruturado encerram o card do mesmo jeito — sem endpoint não há o que coletar
   sem raspar DOM renderizado por JS, fora do padrão dos coletores atuais.
2. Se viável (endpoint estruturado existisse e Termos permitissem): coletor com a interface
   dos atuais (`source_type`, `CollectorCapabilities`, `discover`, telemetria, política de
   rede, retentativa, validador de chave).
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login.
- Navegador headless ou execução de JavaScript para renderizar a lista de vaga.
- Raspagem de HTML/DOM quando não existe endpoint estruturado.

## Resultado da revisão

**Não viável.** Ver a pesquisa citada para o texto completo. Resumo:

- `robots.txt` permissivo (só bloqueia parâmetros de tracking) — não bloqueia `/jobs/`.
- Termos de Uso (`usebraintrust.com/terms`, seção "Prohibited Uses of the Site"): busca por
  "scrape", "harvest", "aggregat", "data mining", "compet(e/itive)" no documento inteiro não
  encontrou nenhuma ocorrência — cláusula genérica ("unauthorized engine, software, tool"),
  mesmo padrão que Workday/Teamtailor/Workable/Factorial (não bloqueante por si).
- Não há API pública documentada; o HTML inicial de `/jobs/` (72.042 bytes) não contém
  `<script type="application/ld+json">` com `JobPosting` — é uma SPA que busca a lista de
  vaga via JS não descoberto nos assets estáticos.
- Sem bloqueio tipo CAPTCHA/DataDome na requisição simples, mas isso é irrelevante: não há
  conteúdo estruturado para ler mesmo sem esse bloqueio.
- Braintrust é marketplace própria — não delega a nenhum ATS que o radar já coleta.

## Critérios de aceite

- [x] Termos e endpoint revisados e registrados antes do código —
      `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`, decisão: não
      viável. Os critérios seguintes não se aplicam.
- [ ] Coletor com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma vaga real coletada via Braintrust. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma chamada de coleta foi feita; as únicas requisições desta
  revisão foram `robots.txt`, `GET /jobs/` (para checar `JobPosting`) e a página pública de
  Termos, listadas na pesquisa citada.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar (compartilhado com F20-57/58/59) | `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md` | Revisão de termos, robots.txt, API e anti-bot dos quatro sites, feita em conjunto. Entregável final deste card: decisão "não viável" para Braintrust. |

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para Braintrust.
- Não raspar o DOM renderizado por JavaScript de `app.usebraintrust.com`.
- Não contornar nenhum anti-bot.

## Pronto quando

A revisão está registrada com decisão e evidência, e o card está marcado como fechado — não
viável, sem código pendente.
