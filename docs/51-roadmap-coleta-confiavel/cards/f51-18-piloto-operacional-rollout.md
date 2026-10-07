# F51-18 — piloto operacional, CI, rollout, rollback e fechamento

- **Status:** Planejado
- **Prioridade:** P0
- **Esforço estimado:** M
- **Risco:** alto: rollout sem evidência compatível pode ampliar coleta parcial ou alterar dados fora da coorte.
- **Dependências:** F51-05; F51-08; F51-12; F51-13; F51-17.

## Problema e evidência

**Fato:** CI verde valida o commit testado, não coleta real, conteúdo útil nem frescor operacional. A SPEC propõe medir descrição útil >=95% em coorte elegível fixa após três inventários completos por fonte, recall manual >=95% e frescor em janela de sete dias; N/D não é zero. Não há prova neste card de que essas metas já foram atingidas.

**Risco:** misturar backfill com inventário, atribuir execução a imagem/commit diferente, ou tratar fonte suspensa/desconhecida como sucesso eleva artificialmente a cobertura. F14-F16 podem ser adiados sem impedir fechamento do núcleo e não há meta de ativar 18/18 fontes.

## Objetivo e limites

Produzir runbook reproduzível de sete dias, pacote de evidências por fonte e decisão de go/no-go do núcleo. Operação mutável só ocorre após aprovação operacional aplicável e em coorte piloto explícita; qualquer validação de rollback com escrita usa banco `_test` isolado. Este card não ativa fontes, não executa backfill, não muda flags e não autoriza scraping novo. Fora do escopo: fornecedor IA novo, embeddings, coleta sem autorização, login, CAPTCHA, ou mudança de score/veredito determinístico.

## Arquivos existentes

- [SPEC 51](../../51-spec-coleta-confiavel-e-busca.md): metas, denominadores e invariantes.
- [pipeline.yml](../../../.github/workflows/pipeline.yml): CI; registrar URL e SHA do run, sem inferir operação real.
- [doctor.py](../../../scripts/doctor.py): diagnóstico operacional disponível.
- [service.py](../../../src/opportunity_radar/operations/service.py): serviços de operação existentes.
- [worker.py](../../../src/opportunity_radar/worker.py): ciclo de execução; confirmação de runtime exige imagem/commit correspondente.

## Tarefas executáveis

1. Criar manifesto de janela com UTC início/fim, commit, digest da imagem em execução, configuração não secreta, versão de coletor/parser, fontes elegíveis, política de exclusão, coorte fixa e responsáveis. Para CI, gravar URL, SHA e resultado literal dos checks; divergência entre SHA testado e runtime suspende go.
2. Em sete dias, registrar por fonte agenda/tentativas e último inventário completo bem-sucedido separadamente; falha recente não renova frescor. Para cada fonte piloto, anexar três `SourceRun` completos distintos. Backfill não conta como run. Fonte em cooldown aparece degradada e permanece no denominador se elegível; indisponível sem medição é N/D com motivo.
3. Calcular descrição útil sobre coorte elegível congelada: vagas canônicas distintas, descrição útil, ausentes, duplicatas, skips e conflitos. Aplicar a definição da SPEC; texto de erro/título isolado não conta. Para recall manual, incluir elegíveis publicados descartados erroneamente; exclusões só por anotação humana de fora de escopo/permissão.
4. Montar matriz go/no-go por fonte e global com numerador, denominador, query/manifesto, janela e limiar: descrição útil >=95%, três inventários completos por fonte; recall manual >=95%; frescor dentro da janela de sete dias; execução IA terminal 100% observada quando houver operação registrada, sem confundir terminal com sucesso. Qualquer N/D ou população vazia bloqueia conclusão da respectiva métrica.
5. Antes de qualquer backfill/alteração operacional autorizada, gerar dry-run, backup com identificação de escopo e restaurar em ambiente isolado; comparar integridade e registrar hashes/manifests. Simular abort/drain/fence e rollback seletivo em `_test`; nunca usar restore experimental no banco operacional.
6. Emitir decisão assinada com go/no-go, limites de tráfego/coorte, flags exatas, proprietário, janela de observação e comando de parada. Expansões F14-F16 recebem status próprio: aprovadas apenas com autorização/evidência; caso contrário adiadas sem bloquear o núcleo.

## Critérios de aceite

| ID | Critério mensurável | Given / When / Then | Teste/artefato |
| --- | --- | --- | --- |
| AC01 | Pacote contém janela de sete dias e três inventários completos por fonte piloto; backfill não conta. | Dada fonte com dois runs completos e um backfill, quando matriz é calculada, então requisito de três runs falha e go fica bloqueado. | Runbook versionado, IDs de runs e relatório por fonte. |
| AC02 | Métricas exibem numerador, denominador e N/D; metas da SPEC não são inferidas de ausências de dados. | Dada métrica sem amostra ou com fonte em cooldown, quando relatório é gerado, então valor é N/D/degradado e a fonte elegível não some do denominador. | `test_rollout_metrics_keep_unknowns_and_cooldown_visible` (proposto); matriz reproduzível. |
| AC03 | Evidência CI/runtime é compatível em SHA e imagem. | Dado CI para SHA diferente do commit/digest observado no worker, quando gate é avaliado, então decisão é no-go até compatibilizar e anexar URL/sha/saída literal. | Manifesto de runtime, digest, URL do workflow e logs resumidos. |
| AC04 | Backup/restauração e rollback são exercitados somente em ambiente isolado. | Dado snapshot de fixture em `_test`, quando restore e rollback seletivo rodam, então hashes esperados conferem e nenhum comando aponta para DSN operacional. | `test_rollout_restore_and_selective_rollback_isolated` (proposto); manifesto/hash antes/depois. |
| AC05 | Expansão não é requisito de fechar núcleo nem há claim 18/18 sem evidência. | Dadas F14-F16 adiadas, quando o núcleo atende seus gates, então relatório fecha núcleo e lista expansões adiadas; qualquer meta não atingida ou N/D impede go daquela fonte/métrica. | Decisão go/no-go assinada e estados separados por card/fonte. |

## Falhas, interrupção e rollback

Abortar expansão diante de run parcial, divergência de imagem, N/D, queda abaixo dos limiares, erro de permissão/SSRF ou restore não verificado. Parar novas claims, drenar trabalho elegível e aplicar fencing antes de liberar ownership; não marcar ausentes em run parcial. Rollback limita-se às flags/coorte e versão do manifesto, preservando payload bruto, evidência e alterações humanas. Restore é validado isoladamente antes de qualquer plano operacional. Entregáveis: runbook de sete dias, pacote CI/runtime, tabela de métricas, inventários por fonte, prova de restore/rollback isolada e decisão assinada. Nenhuma implementação ou execução operacional é declarada por este card.

## Preparação do pacote (2026-10-07, sexta sessão)

Feito antes do fim da janela, sem dado estimado:

- **Coorte congelada:** as 276 fontes habilitadas e criadas antes da abertura da janela
  (2026-10-07 13:23:48 UTC), em [f51-18-coorte-2026-10-07.tsv](../f51-18-coorte-2026-10-07.tsv):
  98 inHire, 65 Ashby, 56 Greenhouse, 19 Workday, 15 Lever, 11 Workable, 7 Teamtailor, 2
  Factorial, 1 Remotive, 1 Hacker News e 1 manual. As fontes inHire cadastradas depois (lote
  do F52-06) ficam fora da coorte.
- **Runtime no início:** stack `opportunity-radar-dev` construída em 2026-10-07 13:24:18 UTC
  a partir de `b6d25ae`; imagem do worker
  `sha256:dd316ee9512d1addf0a1918ecb925f36927e013a4034420a5f2b8dd5d803a764`, da API
  `sha256:80304800993d5ea875e5384fb1e35902fdf36156eeeeb8ac5eabd647e10b6b4b`.
- **Linha de base:** a medição do [F51-01](f51-01-baseline-benchmark-auditavel.md).

**O que o validador vai exigir e hoje não existe:**

- recall humano de 95% ou mais por fonte: depende da amostra do dono (F51-02). Sem ela o
  validador devolve N/D e a decisão é no-go, mesmo com a janela completa;
- restauração e rollback demonstrados em ambiente `_test`, com hashes comparados;
- aprovação assinada pelo responsável;
- três inventários completos por fonte dentro da janela. Em 2026-10-07 havia 43 fontes sem
  três execuções completas em sete dias; na passada das 14:00 UTC, 86 das 264 respostas foram
  `304`, e essas execuções saem com `complete=false`.

Qualquer PR de código da SPEC 51 mesclado reabre a janela na data do merge e troca o SHA e a
imagem acima. A data vigente está no [README do roadmap](../README.md).
