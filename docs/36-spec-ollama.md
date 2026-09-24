# SPEC — Camada local de IA: respostas, tempo, busca e operação

- **Status:** Proposta, para revisão
- **Data:** 2026-09-23
- **Escopo:** tudo o que o Opportunity Radar faz com o Ollama — análise semântica,
  desempenho, busca, observabilidade, avaliação e operação
- **Hardware de referência:** Xeon E5-2680 v4, 16 GB de RAM, RTX 5060 8 GB (§3.1)
- **Documentos relacionados:** [SPEC de busca](37-spec-busca.md), [Ollama e prompts](21-ollama-prompts.md),
  [Matching e scoring](20-matching-scoring.md), [Tecnologias](05-tecnologias.md) (§ pgvector),
  [Runbook](30-runbook.md)

---

## 1. Objetivo

A camada de IA existe desde a Fase 10 e funciona no sentido estreito: chama um modelo local,
valida o JSON, degrada sem quebrar o fluxo determinístico. Esta SPEC trata do sentido amplo.
A análise precisa ler a vaga de verdade, responder em português, caber no tempo de uma
fila que roda sozinha, deixar rastro do que custou, poder ser comparada entre versões e,
onde isso se pagar de forma medida, apoiar a busca.

Duas coisas não mudam, e cada requisito abaixo é conferido contra elas:

```text
1. o resultado determinístico é a autoridade: nenhuma saída de modelo altera
   elegibilidade, score, veredito ou fator;
2. a IA é opcional: com o Ollama fora do ar, o radar coleta, normaliza, avalia e mostra
   tudo, só sem o comentário.
```

---

## 2. Estado verificado

Auditoria contra o código em 23 de setembro de 2026.

| Área | O que existe | Onde |
| --- | --- | --- |
| Chamada | `POST /api/chat`, `stream: false`, `format` = JSON Schema, `temperature: 0` | `matching/ollama.py:196` |
| Conexão | um `httpx.AsyncClient` novo a cada análise | `matching/ollama.py:103` |
| Opções do modelo | só `temperature`; sem `num_ctx`, `num_predict`, `seed`, `keep_alive` | `matching/ollama.py:201` |
| Entrada | snapshot estruturado: modo, senioridade, contratos, skills, remuneração, prioridade | `matching/service.py:372` |
| Texto da vaga | **não enviado**: sem título, descrição, empresa, localização | `matching/service.py:387-407` |
| Perfil | skills, países e preferências; **sem experiências nem projetos** | `matching/service.py:410` |
| Prompt | `opportunity_analysis/v1`, em inglês; idioma da saída não especificado | `prompts/opportunity_analysis/v1/` |
| Retentativa | 1 retentativa, 0,5 s de espera; timeout de leitura de 30 s | `platform/config.py:17-20` |
| Cache | LRU em memória de 256 entradas por processo, e a própria tabela de análises | `matching/ollama.py:44` |
| Fila | worker com lote de 10 e concorrência 1; lease de claim de 900 s | `worker.py`, `platform/config.py:34-37` |
| Persistência | status, falha, conteúdo, `model_id`, `prompt_version`, `cache_key` | `matching/models.py:200` |
| Medição | **nenhuma**: sem duração, tokens, tempo de carga ou fila | — |
| Avaliação | `examples.json` com saídas de referência, lidas só por teste | `prompts/.../examples.json` |
| Busca | `LIKE` em título e empresa, sem descrição, sem sinônimo | `dashboard/queries.py:345` |
| Imagem | `ollama/ollama:0.5.13`; `pull` do modelo manual (`runbook`) | `compose.yaml`, `docs/30-runbook.md:211` |
| Modelo | `llama3.2:3b` em todos os usos; `OLLAMA_MODEL_OUTREACH/INTERVIEW` declarados e não usados | `.env.example:42-44` |

### 2.1 O que isso significa

- **A análise comenta a planilha, não a vaga.** Sem título e descrição, o modelo não tem
  como apontar uma responsabilidade que não bate com o perfil, uma exigência escondida no
  texto ou uma contradição entre o anúncio e os campos. O que sobra para ele é reescrever
  em prosa os fatores que o motor determinístico já calculou. É a maior perda de valor da
  camada, e nenhuma otimização de tempo compensa isso.
- **Mandar o texto tem custo.** Uma descrição de vaga costuma ter centenas de palavras — a
  distribuição real do acervo é a primeira coisa que o F16-03 mede. Com o
  contexto padrão do servidor e sem `num_ctx` explícito, um prompt maior que a janela é
  truncado pelo início, que é onde estão as instruções de sistema. O servidor registra
  isso no próprio log, mas a resposta a quem chamou não diz nada: para o radar, a
  truncagem é silenciosa. Levar o texto sem orçar tokens é trocar um problema visível por
  um invisível.
- **O tempo não é conhecido.** Não há como dizer hoje quanto leva uma análise, quanto disso
  é carga de modelo, e se o timeout de 30 s corta respostas que teriam terminado.
- **Nada permite comparar versões.** Mudar prompt ou modelo hoje é aposta: não há conjunto
  fixo de casos nem métrica de qualidade para dizer se `v2` é melhor que `v1`.

---

## 3. Metas mensuráveis

### 3.1 Hardware de referência

| Peça | Especificação | O que decide |
| --- | --- | --- |
| CPU | Intel Xeon E5-2680 v4 — 14 núcleos / 28 threads, AVX2, **sem AVX-512** | inferência em CPU é o caminho lento; serve de reserva, não de padrão |
| RAM | 16 GB | divide espaço com Postgres, API, worker e frontend; modelo em RAM disputa com o banco |
| GPU | NVIDIA RTX 5060, **8 GB de VRAM**, arquitetura Blackwell | é onde a inferência deve rodar; o limite real é a VRAM |

Três consequências para esta SPEC:

- **A GPU é o caminho padrão, não um perfil opcional.** Um modelo de 7–8B em Q4_K_M ocupa
  cerca de 5 GB de VRAM, e o que sobra dos 8 GB é o cache de contexto (KV). Com
  `OLLAMA_KV_CACHE_TYPE=q8_0` e flash attention, uma janela de 8 192 tokens cabe junto.
  Modelos de 12B ou mais em Q4 não cabem com contexto útil e transbordam para a RAM, o que
  derruba a velocidade e compete com o Postgres: ficam fora da comparação (§8.1).
- **Hoje a análise roda em CPU, com certeza.** O serviço `ollama` do `compose.yaml` não
  reserva nenhuma GPU, então o container não enxerga a RTX 5060, qualquer que seja a
  versão. E a GPU, quando reservada, exige servidor recente: Blackwell precisa de CUDA 12.8
  ou superior, e a imagem `ollama/ollama:0.5.13` é muito provavelmente anterior a esse
  suporte — o F16-09 confirma. Reservar a GPU e atualizar a imagem deixam de ser melhoria e
  viram **pré-requisito** (F16-09 sobe na ordem, §11), com verificação explícita de que o
  modelo carregou na VRAM (`/api/ps`, campo `size_vram`).
- **Docker no Windows passa pelo WSL2.** A GPU chega ao container pelo Docker Desktop com
  backend WSL2 e o driver NVIDIA do Windows. O runbook ganha esse passo, e o `doctor` passa
  a recusar a análise habilitada com o modelo carregado fora da VRAM.

`OLLAMA_NUM_PARALLEL=1`: cada requisição paralela reserva outro cache de contexto, e com
8 GB isso cabe em uma, não em duas. `OLLAMA_MAX_LOADED_MODELS=2` só quando o modelo de
embedding (§7.2) existir, porque ele é pequeno (menos de 1 GB) e pode ficar residente ao lado
do modelo de análise.

### 3.2 Metas

Os números de latência são estimativas para 7–8B em Q4 nessa GPU — geração na casa de
dezenas de tokens por segundo e avaliação do prompt na casa dos milhares. O F16-01 mede o
valor real antes de qualquer otimização, e as metas são recalculadas a partir dele se a
medição cair fora da faixa. Cada meta tem a medição que a prova, na §9.

| Meta | Hoje | Alvo |
| --- | --- | --- |
| Análise que lê título e descrição da vaga | 0% | 100% das análises com descrição disponível |
| Prompt truncado sem aviso | desconhecido | 0, com contagem de tokens antes do envio |
| Análise em pt-BR | não especificado | 100% dos campos textuais |
| Latência p50 com modelo aquecido, na GPU | não medida | ≤ 8 s |
| Latência p95 com modelo aquecido, na GPU | não medida | ≤ 15 s |
| Análises executadas com o modelo inteiro na VRAM | 0% (compose sem GPU) | 100% |
| Primeira análise após ociosidade (carga do modelo) | não medida | ≤ 1,5 × p95, com aquecimento no início do worker |
| Análises que falham por timeout | não medida | < 2% em janela de 7 dias |
| Taxa de `SCHEMA_MISMATCH` / `INVALID_JSON` | não medida | < 1% |
| Análises reaproveitadas pelo cache persistente após reinício | 0% (cache em memória) | 100% das chaves já gravadas |
| Qualidade no conjunto de avaliação (§8) | inexistente | nota ≥ baseline `v1` em todos os critérios, e maior em fidelidade |
| Busca que encontra por termo da descrição | não | sim, com Postgres full-text |

---

## 4. Frente A — Qualidade da resposta

### 4.1 Levar a vaga ao modelo

- Acrescentar ao payload um bloco `posting`, separado do snapshot determinístico:
  `title`, `company_name`, `location_text` e `description`. O snapshot continua como está,
  porque ele é a identidade da avaliação e entra no `input_hash`.
- A descrição entra **limpa e orçada**: HTML removido, espaços colapsados, seções de
  boilerplate reconhecidas descartadas ("About us", "Equal opportunity", "Benefits"
  genéricos), e o resultado cortado por orçamento de tokens (§5.2), nunca por caracteres
  no meio de uma palavra. O corte é registrado no payload (`description_truncated: true`)
  para o modelo saber que não viu tudo.
- O `content_version` da oportunidade já entra na chave de cache. Mudar o texto da vaga,
  portanto, já invalida a análise, sem regra nova.

### 4.2 Levar o perfil ao modelo

- Acrescentar ao perfil um resumo das experiências e projetos: cargo, empresa, período,
  tecnologias e uma linha de descrição por item, os 5 mais recentes. Esse resumo sai da
  versão do perfil, que já entra na chave de cache.
- O perfil não inclui dados de contato nem nada que não sirva para comparar com uma vaga.

### 4.3 Prompt `v2`

- `prompts/opportunity_analysis/v2`, criado ao lado do `v1`, que continua carregável. A
  troca é por configuração (`OLLAMA_ANALYSIS_PROMPT=v2`), e as análises antigas guardam o
  `prompt_version` com que foram feitas.
- Saída em **português do Brasil**, declarada no system prompt e conferida pelo avaliador
  (§8).
- Instruções que usam o texto: apontar exigências do anúncio ausentes do perfil, citar o
  trecho da vaga que sustenta cada força ou risco, separar o que o anúncio afirma do que o
  modelo inferiu.
- Schema `analysis-v2`: cada item de `strengths` e `risks` passa a ser
  `{ "claim": string, "evidence": string | null }`, onde `evidence` é o trecho literal da
  vaga ou do perfil. O validador confere que o trecho aparece no payload enviado.
  Afirmação com evidência inventada é `SCHEMA_MISMATCH`, não resposta aceita.
- O schema continua sem score, sem elegibilidade e sem desqualificador. O validador
  continua recusando campo desconhecido.
- Poucos exemplos no prompt (1–2, curtos) só se o avaliador mostrar ganho. Exemplo custa
  token em toda chamada.

### 4.4 Determinismo

- `seed` fixo em `options`, junto com `temperature: 0`, para que a mesma entrada no mesmo
  modelo produza a mesma saída. Isso é o que torna a comparação entre versões (§8) justa.
- `top_k`/`top_p` explícitos no `metadata.yaml` da versão do prompt, para que a
  configuração de amostragem seja parte do artefato versionado e não um padrão do servidor.

---

## 5. Frente B — Contexto e tokens

### 5.1 Contexto explícito

- `num_ctx` explícito em toda chamada, configurável (`OLLAMA_ANALYSIS_NUM_CTX`, padrão
  8192). A janela nunca fica por conta do padrão do servidor, que muda entre versões.
- `num_predict` explícito (`OLLAMA_ANALYSIS_NUM_PREDICT`, padrão 768): o limite de saída
  corta resposta que desanda, em vez de deixar o modelo gerar até o timeout.

### 5.2 Orçamento antes do envio

- Estimar os tokens do prompt montado antes de enviar. A primeira versão usa o tokenizer do
  próprio servidor, contando pela resposta de uma chamada de aquecimento
  (`prompt_eval_count`) e calibrando uma razão caracteres/token por modelo. A estimativa
  fica persistida por modelo.
- Orçamento: `num_ctx − num_predict − margem de 10%`. A descrição (§4.1) é a única parte
  elástica: system prompt, snapshot e perfil são fixos, e o que sobra é o espaço da
  descrição.
- Se nem a parte fixa couber, a análise não é enviada: falha classificada como
  `CONTEXT_OVERFLOW` (código novo). Nunca truncamento silencioso.
- Toda análise grava `prompt_tokens` (o `prompt_eval_count` real devolvido) e a estimativa
  feita antes. A diferença entre as duas é o indicador de calibração.

---

## 6. Frente C — Tempo e vazão

### 6.1 Conexão e modelo quentes

- Um `httpx.AsyncClient` por processo, com pool de conexões, em vez de um cliente novo por
  análise. O adaptador já é construído uma vez por processo (`cached_analysis_adapter`); o
  cliente passa a acompanhá-lo, com fechamento no encerramento do worker e da API.
- `keep_alive` explícito por chamada (`OLLAMA_KEEP_ALIVE`, padrão `30m`), para que a fila
  não pague a carga do modelo a cada lote.
- **Aquecimento** no início do worker e antes de cada lote após ociosidade maior que o
  `keep_alive`: uma chamada mínima (`num_predict: 1`) que carrega o modelo e mede a
  calibração de tokens (§5.2). A carga passa a ser um evento medido do worker, não o
  primeiro item da fila pagando por ela.

### 6.2 Timeouts pelo que se sabe

- Separar o timeout de carga do timeout de geração. Com aquecimento, o timeout da análise
  deixa de absorver a carga do modelo. O valor passa a derivar do p99 medido (§9), com
  piso de 30 s e teto de 120 s, em vez de um número fixo escolhido antes de haver medição.
- Retentativa só para falha de transporte e 5xx, com backoff exponencial e jitter. Timeout
  não é retentado de imediato: um modelo que estourou o tempo com essa entrada tende a
  estourar de novo, e a retentativa já é papel do cooldown da fila (`analysis_retry_*`).

### 6.3 Vazão da fila

- Concorrência do worker alinhada ao servidor: `WORKER_ANALYSIS_CONCURRENCY` igual a
  `OLLAMA_NUM_PARALLEL` (padrão 1 em CPU). Mandar duas requisições para um servidor que
  atende uma só enfileira no Ollama, que já tem fila.
- Ordem da fila por valor: `HIGH_PRIORITY` e `RECOMMENDED` antes de `WATCHLIST` e
  `REVIEW_REQUIRED`, e dentro de cada veredito, publicação mais recente primeiro. Com a
  fila atrasada, o que o operador vai ler primeiro é o que fica pronto primeiro.
- Configuração do servidor aplicada no compose, com medição antes e depois (§9):
  `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0`. As duas reduzem a memória do
  cache de contexto, e é isso que permite modelo de 7–8B e `num_ctx` de 8 192 caberem juntos
  nos 8 GB de VRAM da referência (§3.1). `OLLAMA_NUM_PARALLEL=1` pelo mesmo motivo.

### 6.4 Cache que sobrevive

- Antes de chamar o modelo, consultar a tabela de análises pela `cache_key` e reaproveitar
  uma análise `AI_COMPLETED` com a mesma chave. Hoje o reaproveitamento é só em memória e
  morre a cada reinício do worker.
- O LRU em memória continua como primeiro nível, e a tabela vira o segundo. A chave não
  muda: ela já cobre modelo, prompt, schema, versão da vaga e versão do perfil.

---

## 7. Frente D — Busca

A busca é onde "usar IA" é mais tentador e mais fácil de errar. A ordem abaixo é
proposital: primeiro o que resolve o problema sem modelo; embedding só entra se, medido,
resolver o que sobrou.

### 7.1 Busca textual de verdade (sem IA)

> Detalhada e movida para a [SPEC de busca](37-spec-busca.md), §10, card F17-03. O
> resumo abaixo fica como contexto do gate da §7.2.

- Postgres full-text: coluna `tsvector` gerada a partir de título (peso A), empresa (A),
  skills (B) e descrição (C), dicionário `portuguese` e `english` combinados, índice GIN.
- A Inbox troca o `LIKE` por `websearch_to_tsquery` com ordenação por `ts_rank_cd` quando
  há termo de busca. Com isso, "python remoto sênior" encontra a vaga pela descrição, com
  radicalização e sem depender da ordem das palavras.
- Isso não exige Ollama, não muda com o modelo e cobre a maior parte do que se procura.

### 7.2 Busca semântica, com gate de medição

`docs/05-tecnologias.md` já estabelece que pgvector só entra com um caso medido. Esta
frente define a medição antes da implementação:

- **Conjunto de consultas:** 40 consultas reais do operador, cada uma com as vagas que ele
  considera relevantes marcadas no acervo.
- **Métrica:** recall@10 e nDCG@10 da busca full-text (§7.1) sobre esse conjunto.
- **Gate:** embeddings só entram se um protótipo — modelo de embedding multilíngue servido
  pelo Ollama (`/api/embed`), vetores em memória, sem pgvector — superar o full-text em
  pelo menos 15% de recall@10. Se não superar, a frente termina no §7.1, e o resultado
  fica registrado.
- **Se passar:** pgvector com uma coluna de embedding por oportunidade, calculada pelo
  worker no mesmo passo da normalização e invalidada pelo `content_version`; busca híbrida
  (full-text + vetorial, fusão por *reciprocal rank*); o modelo de embedding versionado
  como o prompt, com reindexação explícita quando ele muda.
- O embedding também serviria para agrupar vagas quase duplicadas entre fontes. A
  deduplicação atual é determinística e continua sendo a autoridade; o uso seria sugerir
  pares para revisão, nunca juntar sozinho.

---

## 8. Frente E — Avaliação

Sem avaliação, as frentes A e B são opinião. Esta frente vem antes de qualquer troca de
prompt ou modelo.

- **Conjunto fixo:** 30 pares vaga/perfil reais, anonimizados, em
  `prompts/opportunity_analysis/eval/`, cobrindo vaga forte, vaga fraca, vaga ambígua,
  descrição longa, descrição em inglês e vaga sem descrição.
- **Critérios, pontuados por caso:**
  - **fidelidade:** toda `evidence` aparece no payload (conferido por código, não por
    modelo);
  - **aderência ao determinístico:** o texto não contradiz o veredito;
  - **cobertura:** as exigências do anúncio que faltam no perfil aparecem em `risks`, contra
    uma lista marcada à mão por caso;
  - **idioma:** saída em pt-BR;
  - **custo:** tokens de entrada e saída, latência.
- **Comando:** `make eval-analysis PROMPT=v2 MODEL=...` roda o conjunto contra o Ollama
  local, grava o relatório em `data/evals/` e compara com o último baseline salvo.
- **Regra de troca:** um prompt ou modelo novo só vira padrão se não piorar nenhum critério
  e melhorar pelo menos um, no mesmo hardware. O relatório entra no PR que faz a troca.
- **CI:** o conjunto não roda no CI, que usa o Ollama falso. O CI confere só o que é
  determinístico: schema, validador de evidência, montagem do payload e orçamento de
  tokens contra uma razão caracteres/token fixa.

### 8.1 Escolha de modelo

`llama3.2:3b` foi escolhido pelo custo de CPU, antes de existir avaliação e antes de a GPU
entrar na conta. Com 8 GB de VRAM, a faixa útil passa a ser 7–8B em Q4_K_M. Comparar pelo
menos três modelos nessa faixa — um da família Llama, um Qwen e um de outra família com bom
português — mais o `llama3.2:3b` atual como baseline, pelos critérios acima, pela latência
na GPU e pela VRAM ocupada com `num_ctx` de 8 192. Modelo que transborda para a RAM está
desclassificado, qualquer que seja a nota. O vencedor vira o padrão do `.env.example` e do
`metadata.yaml`. O relatório fica em `docs/pesquisas/`.

---

## 9. Frente F — Observabilidade

- Gravar em cada análise, a partir da resposta do Ollama: `total_duration`,
  `load_duration`, `prompt_eval_count`, `prompt_eval_duration`, `eval_count`,
  `eval_duration`, e a estimativa de tokens (§5.2). Migração com colunas anuláveis: as
  análises antigas não têm esses dados, e isso aparece como indisponível, nunca como zero.
- Log estruturado por análise com os mesmos números, no formato que o worker já usa.
- `GET /analysis-metrics?window=24h|7d`: p50/p95/p99 de latência, tokens médios de entrada
  e saída, taxa por código de falha, taxa de acerto do cache e tamanho da fila pendente. A
  Visão geral ganha uma linha de apoio no bloco de operação, no mesmo padrão das métricas
  por fonte.
- O `doctor` passa a conferir, além do modelo instalado: versão do servidor, `keep_alive`
  efetivo, modelo carregado (`/api/ps`) e memória usada.

---

## 10. Frente G — Operação

- **Imagem:** atualizar `ollama/ollama` da 0.5.13 para a versão estável corrente com suporte
  a Blackwell (CUDA 12.8+), fixada por versão exata e digest. É pré-requisito para a GPU da
  referência (§3.1). A troca passa pelo conjunto de avaliação (§8) quando ele existir:
  versão de servidor muda tokenizer, padrões e desempenho.
- **Modelo instalado sem terminal:** serviço `ollama-init` no compose, que roda
  `ollama pull` do modelo configurado e termina. O worker depende dele com
  `service_completed_successfully` só quando a análise está habilitada; com ela
  desligada, o radar sobe sem baixar nada.
- **Recursos:** limite de RAM no serviço `ollama` do compose, para que um transbordo da VRAM
  não tome a memória do Postgres nos 16 GB da referência. Um modelo que não cabe deve falhar
  na subida, não derrubar o banco.
- **Configuração enxuta:** remover `OLLAMA_MODEL_OUTREACH` e `OLLAMA_MODEL_INTERVIEW` do
  `.env.example`. Declarar modelo para funcionalidade que não existe é documentação falsa.
- **GPU por padrão:** o serviço `ollama` reserva a GPU NVIDIA (`deploy.resources.
  reservations.devices`), e o runbook documenta o pré-requisito no Windows: Docker Desktop
  com WSL2 e driver NVIDIA recente. Um perfil `cpu` fica como reserva para máquinas sem
  GPU, com as metas de latência da CPU medidas à parte. O CI continua com o Ollama falso.

---

## 11. Plano de entrega

Proposta de fase, na convenção dos roadmaps (`docs/33`, `docs/34`), com um card por linha.
A ordem respeita a dependência real: medir antes de otimizar, avaliar antes de trocar.

| Ordem | Card | Frente | Depende de |
| --- | --- | --- | --- |
| 1 | F16-01 — medir cada análise (durações, tokens, VRAM) | F | Nenhum |
| 2 | F16-09 — imagem com suporte a Blackwell, GPU no compose, `ollama-init`, limites | G | Nenhum |
| 3 | F16-02 — cliente persistente, `keep_alive`, aquecimento | C | F16-01 |
| 4 | F16-03 — `num_ctx`, `num_predict`, orçamento de tokens e `CONTEXT_OVERFLOW` | B | F16-01 |
| 5 | F16-04 — conjunto de avaliação e `make eval-analysis` | E | F16-01 |
| 6 | F16-05 — vaga e experiências no payload, prompt `v2` em pt-BR com evidência | A | F16-03, F16-04 |
| 7 | F16-06 — cache persistente e fila por valor | C | F16-02 |
| 8 | F16-07 — busca full-text na Inbox → movido para F17-03 na [SPEC de busca](37-spec-busca.md) | D | — |
| 9 | F16-08 — comparação de modelos e troca do padrão | E | F16-04, F16-05 |
| 10 | F16-10 — métricas da análise na API e na Visão geral | F | F16-01 |
| 11 | F16-11 — protótipo de busca semântica e decisão pelo gate | D | F17-03 |

F16-09 subiu para o início porque, no hardware de referência, sem ele a análise roda em
CPU e toda medição de latência feita antes seria sobre o caminho errado. F16-07 não depende
de nada desta SPEC e é detalhado na [SPEC de busca](37-spec-busca.md). F16-11 pode terminar
em "não implementar" — esse é um resultado válido, registrado com os números.

---

## 12. Invariantes

- A saída do modelo não altera elegibilidade, score, veredito nem fator.
- Com o Ollama indisponível, nada além do comentário deixa de funcionar.
- Nenhum prompt é truncado sem que isso esteja registrado na análise.
- Toda análise registra modelo, versão de prompt, versão de schema e o que custou.
- Toda troca de prompt, modelo ou versão de servidor passa pelo conjunto de avaliação.
- Nenhum dado do operador sai da máquina: nenhuma frente introduz serviço de IA remoto.

---

## 13. Riscos

| Risco | Mitigação |
| --- | --- |
| Descrição longa estoura a janela e o tempo | orçamento de tokens (§5.2), `num_predict`, limpeza de boilerplate |
| Modelo maior melhora a qualidade e estoura a latência | a regra de troca (§8) exige as duas medidas no mesmo relatório |
| `evidence` inventada que parece plausível | conferência literal por código, não por outro modelo |
| Avaliação com poucos casos dá conclusão frágil | 30 casos cobrindo os tipos listados; diferença pequena não troca o padrão |
| Embedding vira custo sem ganho | gate de recall@10 antes de qualquer pgvector (§7.2) |
| Atualizar o Ollama muda o comportamento em silêncio | imagem fixada por digest e troca só com relatório de avaliação |

---

## 14. Fora de escopo

- Serviços de IA remotos (OpenAI, Anthropic, etc.) ou envio de dados para fora da máquina.
- Modelo decidindo elegibilidade, score ou veredito.
- Geração de carta de apresentação, mensagem de contato ou preparação de entrevista — os
  usos que o `.env.example` sugeria. Se voltarem, é SPEC própria, sobre esta base.
- Fine-tuning de modelo.
- Streaming da análise para a tela: a análise roda na fila, e ninguém espera por ela na
  frente do monitor.
