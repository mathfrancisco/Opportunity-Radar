# CARD F13-03 — Separação do envelope e payload

- **Status:** Concluído em 2026-09-22
- **Fase:** 13 — Operação contínua
- **Depende de:** Nenhum
- **Bloqueia:** F13-04
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§24–26 e risco 5

## Resultado

`RawItem` mantém um envelope imutável de procedência, enquanto `RawItemPayload` guarda
o conteúdo bruto que poderá expirar conforme política posterior.

## Contexto

O payload atual é obrigatório e `RawItem` é imutável. Limpar o campo diretamente
violaria a procedência, o hash e a capacidade de auditar a aquisição.

## Escopo

- Criar estrutura de payload vinculada a `RawItem`.
- Migrar conteúdo bruto existente e fazer backfill idempotente.
- Preservar no envelope `RawItem` a fonte, `SourceRun`, identidade, hash e
  `SourceOccurrence`.
- Validar contagem, vínculo e integridade antes de habilitar qualquer limpeza.

## Fora de escopo

- Expiração de dados, mudança de regras de normalização e descarte do envelope.

## Notas de implementação

Faça a migration em etapas compatíveis: adicionar a estrutura, preencher registros
existentes, validar, mover leitores e só então tornar o novo caminho obrigatório. Não
altere o hash histórico nem recrie `RawItem`; a migration deve preservar IDs e
proveniência.

## Critérios de aceite

- [x] Cada payload existente é preservado após a migration e o backfill.
- [x] Backfill pode ser reexecutado sem duplicar payloads.
- [x] `RawItem` preserva ID, hash, fonte, `SourceRun` e `SourceOccurrence`.
- [x] Leitores atuais obtêm o mesmo conteúdo bruto antes da retenção.
- [x] Validação falha se houver item sem payload onde o legado tinha conteúdo.

## Verificação

Rode migration e backfill contra fixture com itens repetidos e múltiplas fontes;
compare contagens, hashes, IDs, vínculos e conteúdo antes e depois.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/models.py`
- `src/opportunity_radar/acquisition/service.py`
- `src/opportunity_radar/migrations/`
- `tests/acquisition/`
