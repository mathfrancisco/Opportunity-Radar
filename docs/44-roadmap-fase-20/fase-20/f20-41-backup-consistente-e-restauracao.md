# CARD F20-41 — Backup consistente e restauração verificável

- **Status:** Feito — snapshot compartilhado, gate estrito, sha256, relacionamentos e extensões implementados em `scripts/backup.py`/`scripts/restore_check.py`/`src/opportunity_radar/platform/backup.py`; `tests/backend/test_backup.py` cobre a lógica sem Postgres e o round-trip real; `tests/backend/test_backup_restore_integration.py` (novo) prova com Postgres real que uma escrita concorrente durante o dump não causa divergência de contagem; round-trip real (`pg_dump`/`pg_restore`) e RTO/RPO medidos contra Postgres via `docker compose -p f20-pt`, números em `docs/30-runbook.md` §5. As tabelas de IA citadas em "Ajustes da Fase 20" (`ai_quota_usage`, F20-19, F20-16) ainda não existem no código; entram em `MANIFEST_QUERIES` quando esses cards forem feitos.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-08](../../40-roadmap-varredura-produtiva/fase-18/f18-08-backup-consistente-e-restauracao.md)

## Ajustes da Fase 20

- Incluir no backup e na prova de restauração as tabelas novas da IA: `ai_quota_usage`, registros de chamada (F20-19) e cache (F20-16).
- O backup nunca inclui o `.env` nem a `GROQ_API_KEY`.

## Resultado

Backup durante coleta ativa restaura o mesmo estado descrito no manifesto e preserva os dados duráveis do operador.

## Escopo

- Usar snapshot transacional compartilhado/exportado entre manifesto e pg_dump, mantendo-o válido durante dump; alternativa exige janela explícita sem escritores.
- Escrever dump/manifesto atomicamente; registrar hash, tamanho, revisão e versão do formato. Gate estrito rejeita manifesto ausente/incompatível ou checksum divergente.
- Modo somente legibilidade é explícito e não reporta backup verificado. Contagens são insuficientes: conferir amostras de conteúdo/relacionamentos.
- Incluir perfil, candidaturas, marcas, buscas salvas e decisões; atualizar inventário com cada migração. Dados de avaliação fora do banco têm pacote/manifesto próprio.
- Restore em banco descartável exige extensão/imagem compatível, incluindo pgvector quando existir. Documentar retomada e reconstrução de derivados.
- Definir no runbook periodicidade, local de cópia separado, idade máxima tolerada e tempo de recuperação medido; defaults propostos 24 h e 30 min são metas a confirmar.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [x] Escrita concorrente não causa divergência artificial de contagens.
- [x] Sem manifesto/hash válido o gate estrito falha.
- [x] Restauração confere dados e relações, inclusive features já instaladas.
- [x] Procedimento de recuperação tem evidência e limitações registradas.

## Verificação

- **CI:** Backup sob escritor controlado, corrupção/ausência de manifesto, restauração de banco populado e extensão quando aplicável.
- **Máquina de referência:** Restore medido em banco descartável; execução futura somente com autorização explícita.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Critério → evidência

| Critério | Evidência |
| --- | --- |
| Escrita concorrente não causa divergência artificial de contagens | `tests/backend/test_backup_restore_integration.py::test_concurrent_writer_does_not_cause_artificial_count_divergence` (novo, `RUN_DATABASE_INTEGRATION=1`): insere uma empresa numa conexão separada entre o `pg_export_snapshot()` e o `pg_dump`, e prova que a linha concorrente fica fora tanto do manifesto quanto do dump — `compare(...) == []` |
| Sem manifesto/hash válido o gate estrito falha | `tests/backend/test_backup.py::test_load_manifest_missing_file_fails_strict`, `::test_load_manifest_incompatible_format_version_fails_strict`, `::test_verify_checksum_rejects_a_mismatch`, `::test_restore_check_main_fails_on_a_tampered_dump` (round-trip real contra Postgres, `RUN_DATABASE_INTEGRATION=1`) |
| Restauração confere dados e relações, inclusive features já instaladas | `tests/backend/test_backup.py::test_compare_flags_a_broken_relationship`, `::test_compare_flags_a_missing_extension`, `::test_backup_and_restore_round_trip_matches_the_manifest` (round-trip real: dump→restore→`compare()==[]`, inclusive extensão `vector`) |
| Procedimento de recuperação tem evidência e limitações registradas | `docs/30-runbook.md` §5: periodicidade (24 h), RPO alvo (24 h), RTO medido (`scripts/backup.py` ≈1.6 s, `scripts/restore_check.py` ≈2.2 s, ciclo completo ≈3.8 s contra o banco de teste local; ≈6–6.5 s por invocação `make` isolada incluindo subida de container), e a limitação explícita de que o número escala com o volume de dados e não substitui medição contra um dump de produção |

Medição de RTO/RPO rodada em 2026-09-26 contra `docker compose -p f20-pt -f compose.yaml
-f compose.dev.yaml`, banco de teste local (13 tabelas do fluxo vertical, dump de
157 KB). Ver `docs/30-runbook.md` §5 para os números completos e a limitação de escala.

## Arquivos prováveis

`scripts/backup.py`, restore_check.py, platform/backup.py, pipeline.yml e docs/30-runbook.md.

## Contexto no código

`platform/backup.py`, `scripts/backup.py` e `scripts/restore_check.py` já existem e já
implementam a maior parte do fluxo, mas com lacunas concretas encontradas na leitura:

- `MANIFEST_QUERIES` (`platform/backup.py:14-26`) tem uma contagem por tabela do fluxo
  vertical (`company`, `company_source`, `profile_version`, `source_definition`,
  `source_run`, `raw_item`, `opportunity`, `source_occurrence`, `match_assessment`,
  `match_analysis`, `application_process`, `stage_history`) — **não** inclui
  `platform.ai_quota_usage`, `platform.ai_call_record` (F20-19) nem
  `opportunities.field_suggestion` (F20-23). Nenhuma das três tabelas existe ainda nesta
  árvore (criadas por F20-12/F20-19/F20-23); se este card rodar antes delas, registrar
  no PR quais entram como "a confirmar" até a migração correspondente aterrar.
- `scripts/backup.py:collect_manifest` (linhas 36-50) roda sua própria consulta de
  contagem numa conexão separada da que `run_pg_dump` (linhas 53-70) usa para o
  `pg_dump` — **não há snapshot transacional compartilhado ou exportado entre os dois**.
  Sob escrita concorrente, a contagem do manifesto e o conteúdo do dump podem divergir
  sem que isso seja um bug de dado, só falta de sincronização — exatamente o problema do
  critério de aceite 1.
- O manifesto grava `created_at`, `alembic_revision`, `database`, `counts`, `file` e
  `bytes` (`scripts/backup.py:102-109`) — **não grava hash do dump nem versão do
  formato do manifesto**. O critério de aceite 2 ("sem manifesto/hash válido o gate
  estrito falha") não tem hash para verificar hoje.
- `scripts/restore_check.py:main` (linhas 124-157) tem um bug de gate encontrado na
  leitura: quando não há manifesto (`manifest = {}`), a linha 151 calcula
  `problems = compare(manifest, restored) if manifest else []` — como `manifest` é um
  dict vazio (falsy), `problems` fica `[]` e o script imprime **"restore check passed"**
  mesmo sem ter verificado nada. Isso é o oposto do "gate estrito" pedido pelo critério
  de aceite 2: hoje a ausência de manifesto passa, não falha.
- Não há checagem de extensão (`pgvector`) no restore: `smoke_queries`
  (`restore_check.py:87-97`) só roda `MANIFEST_QUERIES`; se `vector` (criada pela
  migração `20260925_0024_opportunity_embedding.py:36`) não estiver disponível na imagem
  de restauração, a falha apareceria como erro de `pg_restore`, não como um item do
  relatório.
- `docs/30-runbook.md` seção 5 (linhas 84-101) já documenta `make backup`/
  `make restore-check` e `BACKUP_RETENTION_DAYS`, mas não define periodicidade, local de
  cópia separado, idade máxima tolerada nem tempo de recuperação medido — os defaults
  propostos pelo card (24h e 30min) ainda não estão escritos em nenhum lugar.
- O backup nunca lê `.env`/`GROQ_API_KEY`: `pg_dump` só despeja o banco Postgres, nunca o
  sistema de arquivos, então a garantia "nunca inclui `.env`" já é estrutural. O risco
  real é as tabelas de telemetria da IA (F20-19) guardarem por acidente algo que remonte
  à chave (corpo de requisição/resposta) — este card não cria essas tabelas, mas deve
  testar que o dump/manifesto delas nunca contém a string `GROQ_API_KEY` nem o valor da
  variável de ambiente, como defesa em profundidade.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/platform/backup.py` | `MANIFEST_QUERIES` com as tabelas novas da IA; `MANIFEST_FORMAT_VERSION` |
| Alterar | `scripts/backup.py` | snapshot transacional compartilhado com `pg_dump` (ou janela explícita sem escritores); hash do dump no manifesto |
| Alterar | `scripts/restore_check.py` | gate estrito: manifesto ausente/incompatível ou hash divergente falha (corrige o bug da linha 151); checagem de `pgvector` |
| Alterar | `docs/30-runbook.md` | periodicidade, local de cópia separado, idade máxima tolerada, RTO medido (seção 5) |
| Criar | `tests/backend/platform/test_backup_manifest.py` | hash, formato, tabelas novas, ausência de `GROQ_API_KEY` |
| Criar | `tests/backend/test_backup_restore_integration.py` | escritor controlado durante o dump, corrupção/ausência de manifesto, restauração com `pgvector` |

Nenhuma migração de schema é criada por este card: as tabelas novas citadas no
manifesto pertencem aos cards F20-12/F20-19/F20-23.

## Interfaces

```python
# src/opportunity_radar/platform/backup.py
MANIFEST_FORMAT_VERSION = "backup-manifest-v2"  # v1 implícito era o formato sem hash

MANIFEST_QUERIES: dict[str, str] = {
    # ... entradas já existentes ...
    "ai_quota_usage": "SELECT count(*) FROM platform.ai_quota_usage",       # F20-12
    "ai_call_record": "SELECT count(*) FROM platform.ai_call_record",       # F20-19
    "field_suggestions": "SELECT count(*) FROM opportunities.field_suggestion",  # F20-23
}

#: Nunca aparecem em dump, manifesto ou log de backup.
FORBIDDEN_MANIFEST_STRINGS: tuple[str, ...] = ("GROQ_API_KEY",)


def dump_sha256(path: "Path") -> str:
    """Hash do arquivo `.dump`, gravado no manifesto para o gate estrito comparar."""


def has_extension(url: str, name: str) -> bool:
    """Confere se `name` (ex.: "vector") está instalada no banco restaurado."""


# scripts/backup.py
def run_pg_dump_with_shared_snapshot(url: str, target: "Path") -> str:
    """Exporta o snapshot da transação que leu o manifesto (`pg_export_snapshot()`)
    e passa `--snapshot=<id>` ao `pg_dump`, para que manifesto e dump vejam o mesmo
    estado. Sem suporte a snapshot exportado, documentar a alternativa de janela
    explícita sem escritores em vez de mascarar a divergência."""


# scripts/restore_check.py
def strict_gate(manifest: dict, restored: dict, *, dump_hash: str) -> list[str]:
    """Substitui `compare`: manifesto ausente, `manifest_format_version`
    incompatível ou hash do dump divergente sempre entram na lista de problemas —
    nunca resultam em lista vazia por manifesto ausente."""
```

## Passos

1. Escrever `tests/backend/platform/test_backup_manifest.py` cobrindo: hash do dump
   presente e correto, `manifest_format_version` presente, as três tabelas novas da IA
   na lista (mesmo com contagem 0 quando as tabelas ainda não existem — registrar como
   "a confirmar" se a migração ainda não aterrou), e ausência de `GROQ_API_KEY` em
   qualquer string do manifesto.
2. Escrever `tests/backend/test_backup_restore_integration.py` cobrindo: escrita
   concorrente durante o dump não gera divergência de contagem (critério de aceite 1),
   manifesto ausente ou com hash divergente falha o gate (critério de aceite 2, cobre o
   bug descrito no Contexto), e restauração com `pgvector` presente (critério de aceite
   3).
3. Adicionar `MANIFEST_FORMAT_VERSION`, `FORBIDDEN_MANIFEST_STRINGS`, `dump_sha256` e
   `has_extension` a `platform/backup.py`; estender `MANIFEST_QUERIES` com as três
   tabelas novas.
4. Em `scripts/backup.py`, exportar o snapshot da transação que roda
   `collect_manifest` (`pg_export_snapshot()`) e repassar para `pg_dump` via
   `--snapshot`; se a versão do Postgres/`pg_dump` não suportar, documentar no runbook a
   alternativa de janela explícita sem escritores em vez de manter a divergência
   silenciosa atual.
5. Gravar `dump_sha256(target)` e `MANIFEST_FORMAT_VERSION` no manifesto
   (`scripts/backup.py:104-109`).
6. Corrigir `scripts/restore_check.py:151`: substituir
   `problems = compare(manifest, restored) if manifest else []` pela chamada a
   `strict_gate`, que sempre reporta manifesto ausente/incompatível/hash divergente como
   problema — nunca devolve "passed" sem ter verificado nada. Manter um modo explícito
   `--readability-only` que declara no output que **não** verificou dados, em vez de
   imprimir "restore check passed".
7. Adicionar a checagem de `pgvector` (`has_extension`) ao `smoke_queries`/relatório do
   `restore_check.py`, com o resultado exposto mesmo quando a extensão não é esperada
   (dado ainda não usa vetores).
8. Atualizar `docs/30-runbook.md` seção 5 com periodicidade, local de cópia separado,
   idade máxima tolerada e RTO medido; marcar 24h/30min como metas a confirmar (não como
   medição real), conforme o card pede.
9. Confirmar amostras de conteúdo/relacionamentos além da contagem (por exemplo, uma
   `MatchAnalysisModel` específica com seus `MatchAssessmentModel`/`SourceOccurrence`
   relacionados) no teste de integração — contagem sozinha é insuficiente pelo critério
   de aceite 3.
10. Rodar o comando de verificação e confirmar os quatro critérios de aceite.

## Testes a escrever

- `tests/backend/platform/test_backup_manifest.py::test_manifest_includes_ai_tables_when_present` — inclui `ai_quota_usage`/`ai_call_record`/`field_suggestions` quando as tabelas existem.
- `tests/backend/platform/test_backup_manifest.py::test_manifest_never_contains_groq_api_key` — nenhuma string do manifesto bate com `FORBIDDEN_MANIFEST_STRINGS` nem com o valor real de `GROQ_API_KEY` do ambiente de teste.
- `tests/backend/test_backup_restore_integration.py::test_concurrent_writer_does_not_cause_artificial_count_divergence` — critério de aceite 1.
- `tests/backend/test_backup_restore_integration.py::test_missing_or_corrupt_manifest_fails_strict_gate` — cobre o bug de `restore_check.py:151`; critério de aceite 2.
- `tests/backend/test_backup_restore_integration.py::test_restore_checks_relationships_not_only_counts` — restaura e confere uma cadeia relacional específica, não só contagens; critério de aceite 3.
- `tests/backend/test_backup_restore_integration.py::test_restore_reports_pgvector_availability` — extensão `vector` presente/ausente aparece explicitamente no relatório.

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/test_backup.py tests/backend/test_backup_restore_integration.py
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-41 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Nota: os testes de manifesto (hash, `format_version`, ausência de `GROQ_API_KEY`) foram
adicionados a `tests/backend/test_backup.py` (arquivo já existente que cobre o mesmo
módulo) em vez de um `tests/backend/platform/test_backup_manifest.py` novo, para não
duplicar a infraestrutura de teste do mesmo assunto.

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
