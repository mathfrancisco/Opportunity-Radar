# F20-32 — Gupy: sem homologação, card fechado como não viável

**Data:** 2026-09-27
**Card:** [F20-32 — Coletor Gupy](../fase-20/f20-32-coletor-gupy.md)

## O que foi pedido

O card F20-32 (sub-card de Gupy do F17-10) pede: revisão de termos primeiro; se viável,
coletor no formato de `LeverCollector`/`WorkableCollector`/`FactorialCollector`, board
falso, wiring em `AcquisitionService._collector_settings`, `build_collector_registry`,
`probing.py` (`PROBE_TYPES`), `proposals.py` (`IDENTIFIER_KEYS`),
`registration.py` (`SUPPORTED_ATS`) e `apps/web`, e por fim homologação de pelo menos uma
empresa real do catálogo.

## O que foi feito

1. Revisão de termos, registrada em
   [`docs/pesquisas/termos-gupy.md`](../../pesquisas/termos-gupy.md), **antes de qualquer
   código**, como o card exige ("A revisão de termos vem primeiro; se o endpoint proíbe
   automação, o card fecha como 'não viável' com a revisão registrada").
2. Verificação independente das duas fontes decisivas, feita nesta sessão (não apenas
   citada de segunda mão):
   - `https://asaas.gupy.io/robots.txt` — buscado e conferido byte a byte: `Allow: /`,
     `Disallow: /companies`, `Disallow: /candidates`. Não bloqueia a página de vagas nem
     o detalhe da vaga.
   - `https://www.gupy.io/termos-de-uso-recrutamento-e-selecao-candidatos` — buscado e
     conferido: a seção de diretrizes gerais do usuário proíbe, para "Usuários em geral",
     "agregar, copiar ou duplicar partes do Gupy Recrutamento e Seleção, incluindo
     oportunidades de trabalho expiradas".
3. **Decisão: não viável.** A cláusula acima descreve, nominalmente, a operação de um
   coletor (ler o board, guardar as vagas, manter histórico mesmo após expirar). É uma
   proibição específica — diferente da cláusula genérica de "não prejudicar o serviço" que
   Workday/Teamtailor/Workable/Factorial tinham e que permitiu aqueles quatro coletores.
   O `robots.txt`, isoladamente, permitiria a leitura; os Termos de Uso, que têm cláusula
   nomeada para esta operação, decidem o caso pela regra do próprio card
   ("Endpoint que proíbe acesso automatizado encerra o sub-card").
4. Card F20-32 atualizado para `Status: Fechado — não viável`, com os quatro critérios de
   aceite marcados `N/A (não viável)` exceto o primeiro (revisão de termos), que está
   cumprido.

## O que não foi feito, e por quê

- **Nenhum código de coletor** (`src/opportunity_radar/acquisition/gupy.py`) foi escrito.
- **Nenhum wiring** em `AcquisitionService._collector_settings`,
  `build_collector_registry` (`registry.py`), `PROBE_TYPES`/`PUBLIC_ENDPOINT_REFERENCES`
  (`probing.py`), `IDENTIFIER_KEYS` (`proposals.py`), `SUPPORTED_ATS`
  (`registration.py`) nem `apps/web/src/components/SourceCreateForm.tsx` /
  `apps/web/src/features/sources/api.ts`. `"gupy"` continua fora de todos esses
  conjuntos, exatamente como estava antes deste card.
- **Nenhum board real de empresa Gupy foi lido, listado ou coletado** — nem sequer em
  chamada manual isolada de teste de coletor, porque não há coletor. As duas únicas
  chamadas HTTP feitas nesta revisão foram a leitura do `robots.txt` de uma conta
  (`asaas.gupy.io`, só para confirmar a política pública) e a leitura da página de Termos
  de Uso da própria Gupy — nenhuma delas é coleta de vagas.
- **Nenhum teste novo, board falso nem alteração de compose** foi criado para este card,
  porque não há comportamento de coletor a testar.

## Por que isto conta como o card concluído, não como pendência

O card F20-32 define, na própria seção "Ajustes da Fase 20", que a revisão de termos é o
primeiro passo obrigatório e que um endpoint que proíbe automação **encerra o sub-card**
— não o deixa pendente para retomar depois. A tabela de "Arquivos" do card também prevê
esse desfecho explicitamente: "Se o endpoint proibir automação, este documento
[`termos-gupy.md`] é o entregável final do sub-card e ele fecha como 'não viável'."
Não há, portanto, trabalho de implementação restante para F20-32 — o card está fechado
pelo motivo previsto nele mesmo.

## Referências

- `docs/pesquisas/termos-gupy.md`
- `docs/44-roadmap-fase-20/fase-20/f20-32-coletor-gupy.md`
- Precedente de decisão positiva (para contraste): `docs/pesquisas/termos-workday.md`,
  `termos-teamtailor.md`, `termos-workable.md`, `termos-factorial.md`, e
  `docs/44-roadmap-fase-20/evidencias/homologacao-real-2026-09-26.md`
