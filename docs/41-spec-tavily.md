# SPEC — Tavily: descoberta web, extração e evidência de fonte

- **Status:** Planejada; nenhuma capacidade abaixo é declarada entregue
- **Data:** 2026-09-25
- **Escopo:** integração do backend com a API REST da Tavily para achar vagas fora dos
  ATS já cobertos, extrair conteúdo de postagens sem corpo e, depois, alimentar propostas
  de fonte com evidência de board
- **Cards de execução:** [Fase 19](42-roadmap-tavily/README.md)
- **Documentos relacionados:** [Fontes e coletores](17-fontes-coletores.md),
  [SPEC de busca](37-spec-busca.md), [SPEC de varredura produtiva](39-spec-varredura-produtiva.md),
  [Runbook](30-runbook.md)

---

## 1. Objetivo

O radar hoje só vê o que um coletor de ATS ou a Remotive sabem listar. Boa parte do
mercado publica vaga em página de carreiras sem ATS conhecido, em board que o catálogo
ainda não identificou, ou em lugar que nenhum coletor cobre. A Tavily é uma API de busca e
extração voltada a agente, com créditos por chamada, e este documento define como o
backend a usa como **mais uma fonte adaptada ao contrato de aquisição existente**, não
como substituto de coletor nem como navegador.

Três usos, nesta ordem de maturidade:

```text
a) descoberta web    — TavilySearchCollector encontra postagens fora dos ATS já
                        integrados, via /search
b) extração          — preenche corpo de postagens/URLs sem descrição, via /extract
c) evidência de fonte — mais tarde, alimenta propostas de fonte da F12-03 quando a
                        busca aponta para um board de ATS já suportado que o radar
                        ainda não coletava
```

**Fora desta SPEC:** Tavily usada do lado do agente — CLI ou skill dentro do Claude/Codex
do desenvolvedor, para pesquisa manual durante o trabalho. Isso não toca o backend do
radar e não tem card aqui.

As duas invariantes do radar valem sem exceção:

```text
1. o resultado determinístico é a autoridade: um resultado de busca não vira
   oportunidade sem passar por normalização, identidade e matching como qualquer
   outro CollectedItem;
2. a Tavily é opcional: sem TAVILY_API_KEY configurada, o radar coleta, normaliza,
   avalia e mostra tudo, só sem a fonte de descoberta web.
```

---

## 2. Decisões

- **Sem dependência nova.** O backend já tem `httpx` como cliente HTTP assíncrono e um
  padrão de retry/telemetria maduro em `acquisition/remotive.py`. Adicionar
  `tavily-python` traria uma segunda forma de fazer a mesma chamada REST, gerenciar
  timeout e retry do jeito da biblioteca, não do resto do projeto — é dependência sem
  necessidade (YAGNI). O `TavilySearchCollector` chama `POST /search` e `POST /extract`
  pelo mesmo `httpx.AsyncClient` injetável que os outros coletores usam.
- **Autenticação.** `Authorization: Bearer <TAVILY_API_KEY>`, chave nova em `Settings`
  (`platform/config.py`, pydantic-settings), opcional. Sem valor configurado, a fonte não
  é uma falha: é relatada como **bloqueada por configuração**, o mesmo tratamento que
  `source_alert_webhook_url` vazio já recebe hoje (comentário em `config.py:72-74`) — a
  ausência é um estado esperado do deployment, não um erro de execução.
- **`auto_parameters` sempre desligado.** O parâmetro existe na API para deixar a Tavily
  escolher profundidade e outros valores sozinha, e pode subir `search_depth` para
  `advanced` sem aviso — dobra o custo em créditos da chamada. O radar sempre envia os
  parâmetros explícitos que decide abaixo; nunca omite para a API decidir.

---

## 3. Fatos da API (Tavily REST)

Base: `https://api.tavily.com`. Plano gratuito: **1.000 créditos/mês**.

### 3.1 `POST /search`

| Parâmetro | Valores | Uso do radar |
| --- | --- | --- |
| `query` | texto livre | palavras-chave do perfil + termos de site (§5) |
| `search_depth` | `basic`\|`fast`\|`ultra-fast` (1 crédito) ou `advanced` (2 créditos) | `basic` por padrão; `advanced` não é usado sem justificativa medida |
| `max_results` | 0–20, padrão 5 | configurável, padrão 5 |
| `topic` | `general` (usado aqui) | sempre `general` — o radar não usa `news` |
| `time_range` | `day`\|`week`\|`month`\|`year` | limitado por configuração (§6), nunca aberto |
| `include_domains` / `exclude_domains` | listas de domínio | inclui boards de ATS conhecidos (§5); exclui o que a Frente 24 do doc 17 já proíbe |
| `include_raw_content` | bool | desligado por padrão — o corpo vem de `/extract` sob cache, não duplicado em toda busca |
| `include_usage` | bool | **sempre `true`** — é como o radar lê créditos gastos por chamada (§6) |

### 3.2 `POST /extract`

- Até **20 URLs por chamada**.
- `extract_depth`: `basic` custa 1 crédito a cada 5 URLs bem-sucedidas; `advanced` custa 2
  créditos a cada 5. O radar usa `basic`; `advanced` fica registrado como opção não
  habilitada até uma medição mostrar que o `basic` perde conteúdo relevante.
- `format`: `markdown` ou `text`. O radar usa `markdown` — mais fácil de auditar no raw
  payload e de limpar depois.

### 3.3 Créditos

Cada chamada com `include_usage=true` devolve o custo em créditos daquela chamada. Isso é
o único jeito confiável de medir gasto: contar chamadas não basta, porque `search_depth`
e o número de URLs bem-sucedidas mudam o custo por chamada.

---

## 4. Cliente e mapeamento de erros

O cliente Tavily segue o desenho de `RemotiveCollector` (retry com `Retry-After`,
telemetria por tentativa, timeout configurável, sem estado global). Mapeamento para
`AcquisitionErrorCode` (`acquisition/domain.py`):

| HTTP | Código existente | Retryable | Observação |
| --- | --- | --- | --- |
| 401 | `SOURCE_UNAUTHORIZED` | não | chave inválida/revogada |
| 403 | `SOURCE_FORBIDDEN` | não | chave sem permissão para o recurso |
| 429 | `SOURCE_RATE_LIMITED` | sim | respeita `Retry-After`, mesmo caminho de `remotive.py:201-224` |
| 5xx | `SOURCE_SERVER_ERROR` | sim | como as demais fontes HTTP |
| timeout de rede | `SOURCE_TIMEOUT` | sim | — |
| erro de transporte/conexão | `UNKNOWN_EXTERNAL_ERROR` | sim | — |
| JSON inválido ou campo esperado ausente | `PARSER_SCHEMA_CHANGED` | não | mesmo padrão de `remotive.py:_jobs` |

**432 e 433 não têm código correspondente hoje** e recebem uma decisão explícita, não uma
aproximação silenciosa:

- **432 (parâmetro fora do plano)** — por exemplo pedir `advanced` sem crédito ou recurso
  fora do plano contratado. É um erro de configuração da chamada, não da rede nem da
  chave: mapeia para `INVALID_CONFIGURATION`, não retryable, com `field` apontando o
  parâmetro (`search_depth` ou `extract_depth`).
- **433 (limite de uso mensal esgotado)** — nenhum código existente descreve "a fonte
  está correta e autenticada, mas o orçamento do provedor acabou". `SOURCE_RATE_LIMITED`
  sugeriria retry em segundos, o que é falso aqui: o limite só reseta no próximo ciclo de
  faturamento. `SOURCE_FORBIDDEN` esconderia que a causa é orçamento, não permissão.
  **Proposta:** acrescentar `AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED` ao enum
  (F19-01), retryable=false, para 433 e para o teto de créditos por execução definido em
  §6. Sem esse código novo, o card usa `SOURCE_FORBIDDEN` como aproximação documentada e
  a diferença fica só no `summary`. A escolha entre as duas fica para a implementação de
  F19-01, registrada no PR.

---

## 5. `TavilySearchCollector`

- `source_type = "tavily_search"`.
- `capabilities = CollectorCapabilities(keyword_search=True)` — mesmo contrato de
  capacidade que a Remotive; o scheduler já sabe pedir busca por palavra-chave sem
  código novo (doc 17, §12).
- **Consulta:** monta `query` a partir de `CollectionRequest.keywords` (cargos-alvo e
  skills de maior peso do perfil, como a Frente D da SPEC de busca já define para a
  Remotive) mais, quando configurado, um recorte por `include_domains` com os boards de
  ATS que o radar sabe coletar (`boards.greenhouse.io`, `jobs.lever.co`,
  `jobs.ashbyhq.com`) para achar empresas ainda não cadastradas nesses ATS.
- **`time_range`:** vem de configuração, nunca `None`/aberto — evita gastar créditos
  redescobrindo o mesmo resultado antigo em toda execução.
- **Mapeamento para `CollectedItem`:** `source_type="tavily_search"`, `url` do resultado,
  `title`, um trecho de `content` como `description` provisória (substituída por
  `/extract` quando o card de extração roda), `raw_payload` com a resposta crua do item.
  Provenance fica em `metadata`, porque `CollectedItem` não tem campo próprio para isso:
  `query`, `rank` (posição no resultado), `score` (relevância que a Tavily devolve),
  `retrieved_at`, `parser_version` (`tavily-search-v1`, seguindo a convenção de
  `_PARSER_VERSION` da Remotive).
- **Dedupe por URL canônica:** antes de emitir, o item é comparado por URL normalizada
  (sem query string de rastreamento, sem fragmento, host em minúsculas) contra os itens
  já emitidos nesta execução e, na normalização, contra o acervo — mesmo princípio de
  identidade que a Frente I da SPEC de busca usa para candidato a duplicata, aplicado
  aqui só à URL, sem heurística de título.
- **Resultado que aponta para ATS já coberto:** quando a URL bate com o padrão de board
  de um ATS com coletor nativo (Ashby, Greenhouse, Lever) e a empresa **não** tem
  `CompanySource` habilitada para aquele board, o item é marcado
  `metadata["source_proposal_candidate"] = True` em vez de virar `CollectedItem` comum
  ingerido normalmente. Ele não é descartado nem ingerido como oportunidade: fica
  disponível para o F19-05 alimentar a F12-03 com evidência, sem duplicar a ingestão que
  o coletor nativo faria melhor.

---

## 6. Orçamento de créditos

Créditos são finitos e compartilhados entre `/search` e `/extract`. Sem controle, uma
consulta ampla em `advanced` esgota o plano gratuito em poucas execuções.

- **Teto por execução:** `tavily_credit_budget_per_run` em `Settings`, um inteiro de
  créditos que a fonte pode gastar numa `SourceRun`. Cada chamada soma o custo que
  `include_usage=true` devolveu; ao ultrapassar o teto, a execução para de fazer novas
  chamadas e termina como `SourceRunStatus.PARTIAL` — não `FAILED`: o teto é uma parada
  esperada, não uma falha de rede ou de dados.
- **Telemetria:** o custo por chamada e o acumulado da execução entram no `SourceRun`
  (`http_requests`/`retry_count` já existem; créditos precisam de um campo próprio —
  card F19-03 decide entre estender `SourceRun` ou registrar em `metadata`
  estruturado, sem duplicar a contagem de HTTP requests que já existe).
- **Estado distinto para teto atingido:** relatado separadamente de erro de rede e de
  429, porque a causa e a ação do operador são diferentes (esperar o próximo ciclo de
  orçamento vs. tentar de novo vs. checar a chave).
- **Cache de extração por hash de URL:** `/extract` nunca roda duas vezes para a mesma
  URL. O card F19-04 guarda o resultado por hash de URL normalizada (mesma normalização
  do dedupe em §5), com validade configurável; uma URL já extraída não volta a gastar
  crédito, mesmo se aparecer em buscas diferentes ou em execuções diferentes.

---

## 7. Privacidade e conformidade

- Nenhuma raspagem de LinkedIn, X/Twitter ou página com login — regra já fixada na
  Frente 24 do doc 17 (`docs/17-fontes-coletores.md`, §24) e que vale para toda a Tavily:
  `exclude_domains` cobre as redes protegidas por padrão, e nenhuma consulta pede
  conteúdo atrás de autenticação.
- Só páginas públicas: a Tavily já opera sobre páginas públicas indexáveis; o radar não
  usa nenhum parâmetro dela que implique navegação autenticada.
- Nenhum dado pessoal além do que a própria postagem de vaga já expõe (a mesma regra que
  os coletores de ATS já seguem — o raw payload é o texto público da vaga, não um perfil
  de pessoa).

---

## 8. Testes

- **`httpx.MockTransport`** para toda chamada a `/search` e `/extract` nos testes
  automatizados — mesmo padrão dos coletores de ATS e da Remotive. Nenhuma chamada real à
  Tavily roda em CI.
- Fixtures cobrem: sucesso com créditos dentro do teto, teto atingido no meio de uma
  execução (`PARTIAL`), 429 com `Retry-After`, 432, 433, 5xx, JSON inválido, resultado
  cujo domínio bate com um ATS já coberto (candidato a proposta), item duplicado por URL
  canônica, cache de extração hit/miss.
- **Smoke manual (fora do CI):** comando único, documentado como candidato de entrada no
  runbook (`docs/30-runbook.md`), para conferir a chave e a conectividade sem gastar mais
  que uma busca:

  ```bash
  TAVILY_API_KEY=... python -m opportunity_radar.acquisition.tavily_smoke \
    --query "backend engineer remote brazil" --max-results 1
  ```

  Custa 1 crédito no plano gratuito (`search_depth=basic`, 1 resultado). Este comando é
  proposto aqui; adicioná-lo ao runbook de fato é edição do card correspondente
  (F19-01), fora do escopo desta SPEC, que é só documentação.

---

## 9. Riscos e perguntas em aberto

- **Ruído de descoberta web.** Busca ampla traz páginas que não são vaga (agregadores,
  listagens antigas, blog de RH). Sem um filtro de "isto é uma postagem de vaga" antes da
  normalização, a Inbox herda o mesmo problema que a Frente F da SPEC de busca já
  descreve para fontes amplas — a mitigação é a mesma: não habilitar em volume antes da
  classificação de área existir.
- **Custo em produção desconhecido.** 1.000 créditos/mês no plano gratuito não foi
  medido contra o volume real de execuções do radar; o teto por execução (§6) é a
  salvaguarda até essa medição existir.
- **Novo código de erro (`SOURCE_QUOTA_EXHAUSTED`) x aproximação com `SOURCE_FORBIDDEN`**
  — decisão explícita adiada para F19-01 (§4); qualquer que seja a escolha, o `summary`
  do erro precisa distinguir as duas causas para quem lê o log.
- **`SourceRun` sem campo de créditos.** Estender o dataclass ou usar `metadata`
  estruturado muda testes existentes de forma diferente; F19-03 decide e documenta a
  escolha no PR, não aqui.
- **Sobreposição com F12-03/F17-09/F18-02.** A Tavily não substitui a descoberta de ATS
  por assinatura em HTML (F17-09) nem a varredura de sitemap (F18-02); ela é uma terceira
  via de achar candidato, e F19-05 precisa registrar de qual via cada proposta veio, para
  não confundir taxas de acerto entre elas.

---

## 10. Fora de escopo

- Tavily do lado do agente (CLI/skills do desenvolvedor) — não é código de produto.
- Navegador headless ou renderização de JavaScript — a Tavily já resolve isso do lado
  dela; o radar não replica.
- Habilitação de fonte sem sonda e homologação — mesmo gate de toda fonte nova
  (`docs/17-fontes-coletores.md`).
- Decidir `search_depth=advanced` ou `extract_depth=advanced` como padrão — fica
  reservado a uma medição futura que mostre perda de conteúdo relevante no `basic`.
- Alterar `dependency` do projeto para incluir `tavily-python` (§2).
