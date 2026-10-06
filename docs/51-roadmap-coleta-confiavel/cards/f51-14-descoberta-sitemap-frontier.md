# F51-14 — descoberta limitada: sitemap, frontier e propostas JSON-LD

- **Status:** Planejado/condicional
- **Prioridade:** P2
- **Esforço:** M
- **Risco:** alto para SSRF, crawling excessivo e habilitação indevida de fonte.
- **Dependências:** F51-13; decisão de fonte/termos antes de qualquer discovery.

## Fatos e escopo

`acquisition/limited_discovery.py` já implementa descoberta limitada por robots, sitemap e HTML, com `DiscoveryLimits` (profundidade, respostas, bytes, URLs e concorrência por host), e verifica redirects/destinos privados. `companies/discovery.py` contém detecção de ATS e checagem de robots. Portanto, este card estende esse mecanismo existente; não constrói crawler paralelo. Descoberta é evidência revisável, não `SourceRun`, coleta ou autorização.

## Arquivos existentes

- [`limited_discovery.py`](../../../src/opportunity_radar/acquisition/limited_discovery.py): `DiscoveryLimits`, execução e reason codes.
- [`discovery.py`](../../../src/opportunity_radar/companies/discovery.py): `detect_ats`, `robots_allows` e assinaturas.
- [`probing.py`](../../../src/opportunity_radar/acquisition/probing.py) e [`registry.py`](../../../src/opportunity_radar/acquisition/registry.py): sondagem e registro de adaptadores.
- [`test_limited_discovery.py`](../../../tests/backend/acquisition/test_limited_discovery.py): limites, robots, redirect privado e loops.
- A persistência de fonte/proposta é responsabilidade do catálogo existente; se não suportar `PENDING`, propor migration mínima sem habilitar `SourceDefinitionModel.enabled`.

## Tarefas executáveis

1. Exigir `source_id`/hostname aprovado, motivo de lacuna medido, owner, termos, data, e limite específico antes de executar. Uma fonte sem decisão humana não abre requests.
2. Reusar `run_limited_discovery`; acrescentar frontier deduplicada por URL normalizada e host, com `max_depth`, máximo de URLs únicas, respostas, bytes por host e bytes agregados. Registrar toda URL descartada e reason code. Não retirar parâmetros identificadores como `id`, `jobId`, `gh_jid`, `ashby_jid` ou tokens opacos que distingam vaga; normalizar apenas ruído documentado.
3. Aplicar validação de URL inicial e de cada redirect, DNS re-resolve/endereços privados e esquema/porta permitidos. Desabilitar redirect automático cego se não garantir validação de cada salto. Rejeitar loop de sitemap e arquivo comprimido que exceda limite de descompressão.
4. Extrair `JobPosting` JSON-LD apenas como sinal para revisão e guardar URL, tipo, contagens, campos observados, profundidade, bytes, hashes/versão do parser e motivo de parada. Não criar RawItem nem fonte executável.
5. Registrar candidato em estado `PENDING`, `enabled=false`; se catálogo atual não possuir estado de proposta, anexar relatório versionado ao fluxo de revisão existente antes de adicionar tabela nova. Aprovação de fonte, termos e adapter permanecem decisão humana separada.

## Critérios de aceite

| ID | Critério mensurável | Given / When / Then | Teste proposto e artefato |
| --- | --- | --- | --- |
| AC01 | Limites de frontier nunca são excedidos. | Dado sitemap aninhado com loop e mais URLs que `max_urls_examined`, quando discovery executa, então requests/bytes/URLs ficam dentro dos caps e termina `LIMIT_REACHED`. | `test_frontier_obeys_depth_url_and_byte_caps` (proposto em `test_limited_discovery.py`); contadores por limite. |
| AC02 | SSRF também bloqueia destino após redirect. | Dada URL pública que redireciona para loopback ou IP privado, quando cada salto é seguido, então destino privado recebe zero conexão e candidato tem reason `POLICY`. | `test_redirect_revalidates_private_destination` (extensão proposta dos testes de redirect existentes); log da cadeia validada. |
| AC03 | Identificadores de vaga sobrevivem à deduplicação. | Dadas URLs iguais exceto `?id=1`/`?id=2`, quando frontier normaliza, então mantém duas chaves e propostas distintas. | `test_frontier_preserves_job_identifier_queries` (proposto); fixture sitemap e URLs finais. |
| AC04 | JSON-LD gera apenas proposta pendente. | Dado página pública com `JobPosting`, quando discovery extrai sinais, então candidato é `PENDING`, `enabled=false` e não existe `SourceRun`/`RawItem`. | `test_jsonld_discovery_creates_pending_disabled_proposal` (proposto); estado do catálogo/relatório. |
| AC05 | Sem aprovação ou com robots disallow não há crawling. | Dada fonte sem decisão aprovada ou robots disallow, quando job tenta discovery, então zero chamadas a sitemap/HTML e reason explícito. | `test_discovery_requires_approval_and_respects_robots` (proposto); contagem HTTP fake. |

## Rollout e reversão

Começar com fixtures e limites padrão já definidos em `DiscoveryLimits`; não rodar em lote sem revisão individual. A proposta fica pendente e desabilitada até owner aprovar termos, endpoint e adaptador. Rollback cancela execução futura e marca proposta como rejeitada/adiada, preservando o relatório de evidência; não apaga fontes nem ativa/desativa coleta existente. Expansão pode ser adiada sem bloquear núcleo. Entregáveis: prova de lacuna, relatório de discovery com limites/razões, candidate PENDING, fixture de segurança e decisão humana. Não houve coleta externa neste card documental.
