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

## D2 ainda pendente

A distinção atual entre `UNKNOWN`, confiança, revisão e o fator correspondente permanece coberta pelo matching existente. Não foi aprovada uma matriz numérica de pesos, missing policy ou thresholds; portanto esta tarefa não altera pontuação nem declara R55-D2 resolvido.

## Versão de senioridade

`seniority-v7` acrescenta somente `Intermediate` como evidência explícita de `MID` em título ou campo estruturado homologado. É uma mudança de classificação versionada; não há migração ou reclassificação automática nesta tarefa. Qualquer reaplicação exige decisão operacional e evidência separada.

Quando o campo estruturado e o título trazem níveis conflitantes, a classificação é `UNKNOWN`. Quando há mais de um nível explícito no próprio título, preserva-se a regra existente que escolhe o maior nível encontrado; esta nota não cria prioridade nova.

## Evidência local R56

No banco PostgreSQL efêmero isolado terminado em `_test`, o gate final concluiu
com saída 0: `2728 passed, 10 skipped` (15 avisos), em 390.97 s. A amostra de
senioridade usou `seniority-v7`, mas contém 300 entradas sem rótulo humano e
portanto não mede precisão. A medição de conteúdo permaneceu bloqueada pelo gate
de ouro humano incompleto (0 de 200 empregos), sem mudança de gold ou pesos.

Esta nota de regras não é evidência do gate do frontend. A validação local de
`apps/web`, quando aplicável, usa o checkout
`C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic`
e o Node 24.19 do runtime Codex; seus resultados e limites são registrados no
artefato de frontend, sem alterar as regras, pesos ou conclusões de backend acima.

## Limite de tráfego preservado — 2026-10-17

A revisão independente da matriz de tráfego não encontrou issues nos manifests, hashes,
rotas, contagens e p50/p95; o recorte final cobre GET v1, escrita e GET v2. Isso não muda as
regras R55. Em particular, a interação Intake ainda faz `submitManualRun` e `normalizeRun`,
duas escritas distintas. Assim, a meta de uma escrita por mutação não está atendida nesse fluxo,
e esta nota não declara aceite completo de todos os critérios.
