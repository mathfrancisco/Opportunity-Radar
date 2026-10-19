# Regras de decisão R55: país, senioridade e estados pendentes

Esta nota registra somente regras R55 já aprovadas e seus limites. Ela não altera pesos,
limiares, políticas de ausência ou aplicação manual.

| Caso | País esperado | Senioridade esperada | Estado/fator esperado |
| --- | --- | --- | --- |
| Descrição: `must be located in Brazil`; localização `Remote, United Kingdom` | `BR`, evidência da descrição | — | País avaliado com a regra explícita |
| Sem frase de elegibilidade; localização `Remote, United Kingdom` | `GB`, evidência estruturada | — | Perfil BR fica inelegível ou em revisão conforme os demais fatos conhecidos |
| País de escritório, `Remote` sem alcance, ou nenhum dado | `()` | — | `UNKNOWN`; não vira global nem descarte automático |
| Duas frases de elegibilidade incompatíveis | `()` | — | `UNKNOWN` e revisão; não há fallback silencioso para localização |
| Título ou campo estruturado homologado `Intermediate`/`Mid` | — | `MID` | Faixa aceita segue o matching determinístico existente |
| `Intermediate English` apenas na descrição | — | `UNKNOWN` | Não infere nível por idioma |
| Perfil aceita Júnior/Pleno e a vaga é Senior | — | `SENIOR` | Penalidade de `SENIORITY_SCOPE`, sem eliminação por esse fator |
| Duas evidências de senioridade conflitantes (campo estruturado versus título) | — | `UNKNOWN` | Revisão/limite existente; sem nível inventado |
| Mais de um nível no mesmo título | — | Maior nível explícito no título | Regra existente de título, sem nova política de prioridade |
| Evidência de senioridade ausente | — | `UNKNOWN` | Revisão/limite existente; sem nível inventado |

## Regras aprovadas preservadas

- A IA é consultiva: não altera score, elegibilidade ou veredito determinístico sem revisão humana.
- Feedback “não é para mim” permanece sugestão manual de perfil; não há auto-score nem ajuste automático nesta tarefa.
- Fechamento aplica-se ao ciclo de vida da oportunidade/ocorrência, não à candidatura manual. Ele exige duas coletas completas consecutivas sem ocorrência e nenhuma ocorrência equivalente ativa. Coleta parcial, `skipped_stale` ou falha não contam como ausência. Retenção de sete dias é política de dados, não fechamento de negócio.

## Evidência e escopo de D2

R55-D2 a D6 chegaram pela `main` depois da evidência inicial desta frente. Preserve os pesos upstream e não atribua sua implementação a R56. A nota inicial abaixo descreve o estado histórico, quando os pesos ainda aguardavam decisão; não representa o estado global atual. A integração local ainda está em andamento e aguarda validação.

## Versão de senioridade

`seniority-v7` acrescenta somente `Intermediate` como evidência explícita de `MID` em título ou campo estruturado homologado. É uma mudança de classificação versionada; não há migração operacional ou reclassificação automática nesta tarefa. Migrations executadas para validar a suíte ocorreram apenas no banco efêmero isolado. Qualquer reaplicação operacional exige decisão e evidência separadas.

Quando o campo estruturado e o título trazem níveis conflitantes, a classificação é `UNKNOWN`. Quando há mais de um nível explícito no próprio título, preserva-se a regra existente que escolhe o maior nível encontrado; esta nota não cria prioridade nova.

## Evidência histórica local R56

Antes dos patches SQL/Intake e da integração, o gate do commit `abd3fbe` concluiu
no banco PostgreSQL efêmero isolado terminado em `_test`, com saída 0:
`2728 passed, 10 skipped` (15 avisos), em 390.97 s. A amostra de
senioridade usou `seniority-v7`, mas contém 300 entradas sem rótulo humano e
portanto não mede precisão. A medição de conteúdo permaneceu bloqueada pelo gate
de ouro humano incompleto (0 de 200 empregos), sem mudança de gold ou pesos.

Esta nota de regras não é evidência do gate do frontend. A validação local de
`apps/web`, quando aplicável, usa o checkout
`C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic`
e o Node 24.19 do runtime Codex; seus resultados e limites são registrados no
artefato de frontend, sem alterar as regras, pesos ou conclusões de backend acima.

## Gate integrado focal — fotografia anterior, 2026-10-18

`npm run check` integrado terminou com saída 0: lint/typecheck, 50 arquivos e
479 testes; build em 2,09 s com aviso de chunk acima de 500 kB. Os testes focados
integrados registraram 304 testes backend aprovados, três avisos em 18,80 s, e
84 testes frontend aprovados. Essa fotografia focal é histórica e não substitui o
gate completo atual, registrado em [backend-validation.md](artifacts/backend-validation.md).
Ela não altera a falta de rótulos humanos para medir precisão.

## Estado histórico de tráfego e patch de Intake — 2026-10-18

A revisão independente da matriz histórica não encontrou issues nos manifests, hashes, rotas,
contagens e p50/p95; o recorte final cobre GET v1, escrita e GET v2. O histórico registra dois
POSTs de Intake (`submitManualRun` e `normalizeRun`). O patch local posterior os combina no POST
`manual-intake`, mas pode executar múltiplas escritas/transações SQL. Em falha de normalização,
retorna erro estruturado com `run_id` para recuperação; o comportamento integrado segue sem
validação. Uma chamada HTTP não equivale a uma escrita SQL. Esta nota não declara aceite completo.

## Gate integrado anterior à correção de `html_text` — fotografia de 2026-10-18

O gate backend completo integrado daquela árvore terminou com 1 falha, 3.176
aprovados, 10 skipped e 32 avisos em 594,58 s. A falha era o caso hostil de
`html_text`, que excedeu o limite de tempo. O patch descrito abaixo foi aplicado
depois desta fotografia; esse resultado não representa o estado da repetição.

## Atualização após revisão e patch — 2026-10-18

A revisão do caso hostil identificou aberturas repetidas de tag sem terminador
como entrada patológica para `HTMLParser`. O patch em
`src/opportunity_radar/platform/html_text.py` só considera uma abertura markup
quando encontra o terminador `>`; o teste de regressão correspondente está em
`tests/backend/platform/test_html_text.py`. O teste `test_html_text` passou 36 testes;
regressões de matching/normalização passaram em 28 testes. Separadamente, `test_regions`,
`test_content_rule_activation` e `test_domain` reportaram `295 passed in 4.97s`.

Na resolução de países, a execução red anterior registrou 3 falhas; após o ajuste
em `regions.py`, a green registrou 4 testes aprovados. Isso cobre os casos de
localização remota e menção de escritório exercitados pelo teste focado; não é
uma medição de precisão geral. Ruff raw terminou com `All checks passed!`; mypy raw
terminou com `Success: no issues found in 149 source files` (logs
`2026-10-18-r56-final-post-regions-ruff.stdout.log` e
`2026-10-18-r56-final-post-regions-mypy.stdout.log`). Os `final-ruff`/`final-mypy`
anteriores são saídas compactadas pelo RTK, não logs raw. Uma tentativa de suíte completa
teve cinco falhas de harness por montagens parciais (workflow ausente e frontend antigo);
após corrigir a montagem para o worktree completo somente leitura, cinco testes focados
passaram em 3,12 s. O gate completo atual terminou com `3181 passed, 10 skipped, 32
warnings in 635.11s (0:10:35)`, conforme
[`artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log`](artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log).
Esse gate local é pré-publicação; push e CI são acompanhados no PR, com integração remota
em andamento e sem afirmação de merge concluído.

As amostras permanecem inalteradas: senioridade tem 300 entradas e nenhuma
rotulada; conteúdo tem 0/200 empregos rotulados. Não há base para afirmar
precisão nem conclusão da fase.
