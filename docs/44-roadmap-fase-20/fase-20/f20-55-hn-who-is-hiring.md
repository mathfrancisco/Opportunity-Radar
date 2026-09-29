# CARD F20-55 — Coletor "Who is hiring?" da Hacker News via API oficial

- **Status:** Feito — mesclado (`9fd4756`), CI verde em `13d6605`; fonte `hacker_news` importada e habilitada na stack real em 2026-09-29 com schedule mensal `0 18 3 * *`.  revisão de termos: viável, ver [`termos-hn-who-is-hiring.md`](../../pesquisas/termos-hn-who-is-hiring.md); execução real: [`hn-who-is-hiring-2026-09-29.md`](../evidencias/hn-who-is-hiring-2026-09-29.md)
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 45](../../45-spec-descoberta-startups.md); pesquisa
  [`docs/pesquisas/descoberta-startups-ats.md`](../../pesquisas/descoberta-startups-ats.md)

## Contexto

O thread mensal "Ask HN: Who is hiring?" concentra vagas postadas em público por
empresas (boa parte startups em estágio inicial). Diferente de Wellfound e YC/WaaS
(F20-51/F20-52, fechados não viável pelos Termos de Uso do site), a Hacker News mantém
uma **API oficial** para acesso programático (`hacker-news.firebaseio.com`, documentada
em `github.com/HackerNews/API`), complementada pela Algolia HN Search
(`hn.algolia.com/api/v1`) para localizar o item do mês sem varrer IDs manualmente. A
pesquisa citada em "Origem" fez uma verificação preliminar (1 busca Tavily) confirmando
que a API existe e não tem cláusula de proibição documentada — **isso não substitui** a
revisão de termos formal exigida por este card antes de qualquer código de coleta.

## Escopo

1. **Revisão de termos**, registrada em `docs/pesquisas/` antes de qualquer código,
   cobrindo: `robots.txt` de `news.ycombinator.com`, texto de `ycombinator.com/legal`
   aplicado especificamente à Firebase API (não ao site — a cláusula "data mining,
   robots, scraping" citada em `wellfound-yc-jobs.md` cobre "your use of the Site"; a
   confirmar se a API é tratada como parte do Site ou como produto próprio), e o
   README/licença de `github.com/HackerNews/API` e de `hn.algolia.com`. Endpoint/cláusula
   que proíbe acesso automatizado encerra o card, mesmo padrão do F20-32/F20-51/F20-52.
2. Se viável: coletor com a interface dos atuais (`source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa), registrado como mais uma fonte
   de busca por palavra-chave — não um coletor de ATS.
3. Se viável: parsing heurístico de comentário de texto livre (empresa, remoto/local,
   stack como sinal) — sem schema.org, sem prometer os mesmos campos estruturados do
   JobPosting (F20-37). Item sem empresa identificável fica pendência, não vaga vazia.
4. Se viável: item cuja empresa aponta para um board de ATS já suportado alimenta a
   mesma fila de proposta do F20-46, com `discovery_via="hn_who_is_hiring"`.

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Raspagem de `news.ycombinator.com` via HTML — só a Firebase API oficial e a Algolia HN
  Search.
- Prometer campos estruturados equivalentes ao JobPosting a partir de texto livre.

## Critérios de aceite

- [x] Termos revisados e registrados antes do código, com decisão explícita
      (viável/não viável) e evidência (robots.txt, texto de termos, README da API).
      Viável com risco residual: `docs/pesquisas/termos-hn-who-is-hiring.md`.
- [x] (Se viável) Coletor registrado, resolve por `source_type` próprio, com teste.
      `hacker_news`; `test_registered_by_source_type_and_probeable`.
      `hacker_news`; `test_registered_by_source_type_and_probeable`.
- [x] (Se viável) Localiza o item do mês corrente via Algolia HN Search sem varrer IDs
      manualmente pela Firebase API.
      `test_locates_current_thread_via_algolia_and_reads_comments_via_firebase`.
- [x] (Se viável) Comentário sem empresa identificável (heurística de parsing falha)
      produz pendência, não item vazio tratado como sucesso.
      Vira `items_invalid` e a execução termina `PARTIAL` (real: 19 de 255).
- [x] (Se viável) Item cuja empresa aponta para board de ATS já suportado gera proposta
      com `discovery_via="hn_who_is_hiring"`, distinto das demais vias.
      `test_ats_board_comment_creates_proposal_tagged_hn_who_is_hiring`; real: 3 propostas.
- [ ] (Não se aplica: viável) (Se não viável) Card fecha com a mesma régua do F20-32/F20-51/F20-52 — decisão
      registrada, nenhum coletor implementado.

## Verificação

- **CI:** (se viável) fixtures de resposta da Firebase API e da Algolia via
  `httpx.MockTransport`; casos de comentário parseável e não parseável; teste de
  registro no `CollectorRegistry`.
- **Máquina de referência:** revisão de termos não faz nenhuma chamada de coleta —
  só `robots.txt`, páginas de termos e o README público da API, mesmo padrão da revisão
  de F20-51/F20-52.

## Arquivos prováveis

- `docs/pesquisas/termos-hn-who-is-hiring.md` (novo, revisão de termos)
- `src/opportunity_radar/acquisition/hacker_news.py` (novo, se viável)
- `src/opportunity_radar/acquisition/registry.py` (se viável)
- `tests/backend/acquisition/test_hacker_news_collector.py` (novo, se viável)

## Não fazer

- Não implementar coletor antes da revisão de termos registrada.
- Não raspar `news.ycombinator.com` via HTML.
- Não contornar limite de taxa ou bloqueio, se algum existir e não estiver documentado
  como ausente.
- Não prometer estrutura de dado que o texto livre do comentário não sustenta.

## Comando de verificação

```bash
docker compose -p f20-55 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_hacker_news_collector.py
docker compose -p f20-55 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-55 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

A revisão de termos está registrada com decisão e evidência; se viável, todos os
critérios de aceite têm evidência, o comando de verificação passa e o CI está verde. Se
não viável, o card fecha como F20-51/F20-52, sem código pendente.
