# CARD F20-71 — Pesquisar e coletar boards de "early careers"/universidade separados do board principal

- **Status:** Feito (rodada 2, 2026-09-29); as 26 fontes foram importadas e habilitadas na stack real no mesmo dia, junto com as 137 (reprocessamento com o normalizador do F20-70 feito) — a rodada 1 (abaixo) não achou boards
  separados; a rodada 2 mudou o método (busca Tavily nos domínios de ATS coletados por
  termos de estágio/junior, sonda do board real) e ativou **26 boards** na `f20manual`,
  todos `SUCCEEDED`: 3227 oportunidades, 193 JUNIOR/INTERN pelo normalizador e 275 por
  título (acervo global antes: 18/2288, 0,79%). Pendente para o real: ativação na pilha
  real (ver `validacao-pendente.md` §4) e F20-70 (regex de estagiário/trainee). Detalhe
  em `evidencias/early-careers-2026-09-29.md` §"Rodada 2". Texto da rodada 1:
  Fechado — não viável. Sondagem real (65 requisições diretas
  às APIs públicas de Ashby/Greenhouse/Lever/Workday, 1 req/candidato, mesma régua do
  F20-27/F20-36/F20-60) contra 8 empresas do catálogo (Nubank, Stripe, Datadog, CI&T,
  Spotify, Adobe, Santander, NVIDIA — nenhuma da lista protegida do F20-60) não
  confirmou nenhum board de early-careers/university **simultaneamente existente e
  populado**. Um achado parcial real: Nubank tem um segundo board (Greenhouse,
  `job-boards.greenhouse.io/nubank`) distinto do Ashby já coletado, mas vazio (0 vagas)
  no momento da sondagem; Adobe tem um site Workday `external_university` que existe mas
  responde `403`/erro `S22` "permission denied" (não é um board público de candidato).
  Nenhum código foi escrito (nenhuma alteração em `src/opportunity_radar/acquisition/`
  ou `scripts/`), nenhuma `source_definition` nova foi criada, nada foi ativado. Métrica
  de JUNIOR+INTERN inalterada: 18/2288 (0,79%), igual ao diagnóstico de origem.
  Evidência completa em
  [`docs/44-roadmap-fase-20/evidencias/early-careers-2026-09-29.md`](../evidencias/early-careers-2026-09-29.md)
  (2026-09-29).
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-03, F20-27, F20-60
- **Origem:** diagnóstico "por que a busca traz tão poucas vagas junior/estágio",
  registrado em
  [`docs/44-roadmap-fase-20/evidencias/diagnostico-vagas-junior-2026-09-28.md`](../evidencias/diagnostico-vagas-junior-2026-09-28.md)
  (2026-09-28). Nenhuma fonte foi pesquisada, sondada ou habilitada durante o
  diagnóstico; este card materializa o que ele encontrou.

## Contexto

No acervo real auditado (2288 vagas, 67 fontes habilitadas), **Ashby (583 vagas em 28
fontes) e Greenhouse (709 vagas em 24 fontes) — 56,5% de todo o catálogo — trouxeram
juntas 1 vaga JUNIOR/INTERN em 1292 (0,08%)**. As 18 vagas junior/estágio do acervo
inteiro vêm de só 5 empresas (Adobe/Workday, CI&T/Lever, Factorial/Factorial,
Lokalise/Greenhouse, Spotify/Lever), nenhuma delas via Ashby.

Cada empresa no catálogo tem exatamente um board configurado
(`source_definition.configuration.board_identifier`/equivalente) — o board principal.
Nenhuma das 67 fontes tem um segundo board de "early careers"/"university"/"campus"
configurado. Verificação pontual: **Nubank** (Ashby, board `nubank`, 119 vagas
coletadas, 0 JUNIOR/INTERN) tem programa de trainee/estágio conhecido no Brasil,
historicamente via Gupy (fechado por ToS, F20-32) ou canal próprio — nenhum board Ashby
separado identificado ainda. Stripe (2 vagas) e Datadog (3 vagas) têm volume baixo
demais no catálogo atual para avaliar se têm board separado.

Ashby, Greenhouse e Lever suportam múltiplos boards/departamentos por empresa (ex.:
Greenhouse permite `department` ou um segundo `board_token` para um site de careers
separado de university/early-careers; Ashby permite múltiplos `jobBoardName` por
organização). Isso não foi confirmado nesta sessão para nenhuma empresa específica —
é hipótese a testar por sondagem real, mesma régua do F20-27/F20-60 (uma requisição
por candidato, endpoint público do próprio ATS).

## Escopo

1. Para as empresas do catálogo com maior probabilidade de ter early-careers program
   conhecido publicamente (Nubank, Stripe, Datadog, e outras do mapa de carreira do
   F20-60 com programa de trainee/estágio divulgado), pesquisar se existe um segundo
   board/departamento no mesmo ATS já configurado para elas.
2. Sondar (1 requisição por candidato, endpoint público, nunca o site institucional)
   os boards encontrados, mesma metodologia do F20-27/F20-60.
3. Para os boards confirmados e populados, revisão de termos (mesma régua do
   F20-32/F20-51/F20-52/F20-60) antes de qualquer `enabled=true`.
4. Adicionar como `source_definition` separada (segundo board da mesma empresa, não
   substituindo o board principal) via `CompanyService.reconcile`/
   `scripts/import_research_catalog.py`, nunca inserção manual.
5. Registrar evidência real de coleta (pelo menos uma vaga JUNIOR/INTERN real) por
   fonte habilitada.

## Fora de escopo

- Corrigir o normalizador de senioridade — ver F20-70; sem essa correção, uma vaga
  "Estagiário" coletada por este card ainda pode cair em UNKNOWN.
- Gupy — fechado pelo F20-32, não reabrir aqui.
- As ~45 empresas do F20-60 sem ATS identificável — não é o mesmo trabalho barato
  deste card.
- Inventar board que não existe: se a sondagem não confirmar um board populado
  separado, a empresa fica registrada como "sem early-careers separado encontrado",
  não como pendência aberta indefinidamente.

## Critérios de aceite

- [x] Pelo menos 3 empresas do catálogo pesquisadas quanto a board separado de
      early-careers/university, com resultado (encontrado/não encontrado) registrado
      com evidência de sondagem real. (8 empresas: Nubank, Stripe, Datadog, CI&T,
      Spotify, Adobe, Santander, NVIDIA — ver evidência.)
- [x] Para cada board confirmado e aprovado na revisão de termos, `source_definition`
      habilitada e pelo menos uma vaga JUNIOR/INTERN real coletada. (N/A — nenhum board
      encontrado atendeu "confirmado e populado" nesta rodada; nada a habilitar.)
- [x] Métrica antes/depois: proporção de JUNIOR+INTERN no acervo real, comparada ao
      0,79% medido no diagnóstico de origem. (Inalterada: 18/2288 = 0,79%, ver evidência
      §4.)

## Não fazer

- Não sondar, coletar ou habilitar nenhuma fonte Gupy.
- Não inserir empresa ou fonte fora do fluxo de reconciliação existente.
- Não assumir que um board de early-careers existe sem sondagem real — o card fecha
  "não viável" para qualquer empresa sem board confirmado, mesma régua do F20-51/F20-52.

## Verificação

- **CI:** suíte de testes de `companies/` e `acquisition/` relevante aos coletores
  tocados.
- **Máquina de referência:** pelo menos uma coleta real de vaga JUNIOR/INTERN por
  fonte habilitada, registrada em `docs/44-roadmap-fase-20/evidencias/`.

## Pronto quando

As empresas pesquisadas estiverem avaliadas (board encontrado e habilitado, ou
confirmado que não existe), com evidência real de coleta para as aprovadas, e a
métrica de JUNIOR+INTERN no acervo real recalculada.
