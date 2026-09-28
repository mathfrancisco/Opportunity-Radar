# CARD F20-58 — Crossover como fonte de vagas

- **Status:** Fechado — não viável. Revisão em
  [`docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`](../../pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md)
  (2026-09-28): `crossover.com/jobs` e as páginas de Termos (`/terms-and-conditions`,
  `/website-terms`) devolvem o mesmo shell React vazio sem executar JavaScript — não há texto
  de Termos citável nem `JobPosting` em `schema.org` no HTML inicial, e não existe API pública
  documentada. Sem endpoint estruturado, a única forma de ler a vaga (ou os próprios Termos)
  é raspar o DOM renderizado por JS — fora do padrão dos coletores atuais, decide o card
  independente do texto de Termos (não confirmado). Nenhum código foi escrito.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); pedido do usuário em
  2026-09-28 ("automatizar coleta de crossover.com/jobs"), tratado com a mesma régua do
  F20-32/F20-51/F20-52.

## Contexto

Crossover (`crossover.com/jobs`) roda seu próprio pipeline de contratação ("Crossover for
Work": testes técnicos, entrevista em vídeo) para vagas remotas full-time. Foi avaliada como
fonte direta de vaga e como possível uso de ATS próprio.

## Escopo

1. **Revisão de termos e de endpoint** registrada em `docs/pesquisas/` antes de qualquer
   código: `robots.txt`, Termos de Uso (texto citável, se obtenível sem JavaScript), API
   pública, autenticação, anti-bot, e se o HTML inicial expõe `schema.org`/`JobPosting`.
   Impossibilidade de obter texto de Termos ou conteúdo de vaga sem executar JavaScript
   encerra o card pela mesma regra de "não raspar DOM sem endpoint estruturado", independente
   do conteúdo do Termo (que fica não confirmado, não aprovado por omissão).
2. Se viável: coletor com a interface dos atuais.
3. Se viável: board falso em `tests/e2e/`, integração com `PROBE_TYPES`/`IDENTIFIER_KEYS`/
   `SUPPORTED_ATS`/formulário de criação de fonte.

## Fora de escopo

- Qualquer fonte que exija login.
- Navegador headless ou execução de JavaScript para renderizar Termos ou lista de vaga.
- Raspagem de HTML/DOM quando não existe endpoint estruturado.

## Resultado da revisão

**Não viável.** Ver a pesquisa citada para o texto completo. Resumo:

- `robots.txt` permissivo (só bloqueia `*/apply$` e `*/next-step`) — não bloqueia `/jobs`, e
  não decide por si mesmo quando bloqueia.
- `https://www.crossover.com/jobs`, `.../terms-and-conditions` e `.../website-terms` devolvem
  o mesmo corpo de 19.434 bytes (SPA React servida via CloudFront/S3), com só
  `Organization`/`WebSite` em `schema.org` — sem `JobPosting`, sem texto de Termos, sem lista
  de vaga no HTML inicial. Não foi possível obter texto citável de Termos sem executar
  JavaScript — diferente dos outros três sites revisados na mesma pesquisa, todos lidos por
  fetch simples.
- Nenhuma API pública documentada encontrada.
- Crossover roda pipeline de contratação próprio — não delega a nenhum ATS que o radar já
  coleta.

## Critérios de aceite

- [x] Termos e endpoint revisados e registrados antes do código —
      `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md`, decisão: não
      viável (por ausência de endpoint estruturado e de Termos legíveis sem JS, não por
      cláusula nomeada confirmada). Os critérios seguintes não se aplicam.
- [ ] Coletor com teste. — N/A (não viável)
- [ ] Sonda, proposta, cadastro e formulário reconhecem a fonte nova. — N/A (não viável)
- [ ] Pelo menos uma vaga real coletada via Crossover. — N/A (não viável)

## Verificação

- **CI:** nenhuma — nenhum código foi escrito.
- **Máquina de referência:** nenhuma chamada de coleta foi feita; as únicas requisições desta
  revisão foram `robots.txt` e as três páginas citadas (`/jobs`, `/terms-and-conditions`,
  `/website-terms`), listadas na pesquisa citada.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar (compartilhado com F20-56/57/59) | `docs/pesquisas/boards-braintrust-careerflow-crossover-landingjobs.md` | Revisão de termos, robots.txt, API e anti-bot dos quatro sites, feita em conjunto. Entregável final deste card: decisão "não viável" para Crossover. |

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para Crossover.
- Não executar JavaScript nem usar navegador headless para ler Termos ou lista de vaga.
- Não raspar o DOM renderizado de `crossover.com`.

## Pronto quando

A revisão está registrada com decisão e evidência, e o card está marcado como fechado — não
viável, sem código pendente.
