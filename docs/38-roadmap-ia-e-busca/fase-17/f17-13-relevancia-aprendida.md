# CARD F17-13 — Relevância aprendida a partir das marcações

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01, F16-09
- **Bloqueia:** Nenhum
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §13.1

## Resultado

Cada vaga recebe uma probabilidade de ser relevante para o operador, aprendida das
marcações que ele mesmo fez. A Inbox pode ordenar por essa probabilidade ao lado do score
determinístico — como sinal que se soma, nunca como decisão.

## Contexto

O F17-01 cria a marcação "relevante / não é para mim" e o F16-09 dá a cada vaga um vetor
do `qwen3-embedding:0.6b`. Com os dois, existe o que falta para aprender o gosto do
operador sem gerar texto: um classificador pequeno sobre vetores congelados.

A ideia vem do padrão do **CLM** (Contrastive Language Models,
[github.com/Contrastive-LM/CLM](https://github.com/Contrastive-LM/CLM), v0.1, Apache-2.0):
um codificador congelado com uma cabeça pequena e treinável que responde "verdadeiro ou
falso com probabilidade" (*Noul*) ou "qual destas opções" (*Choice*) em milissegundos, sem
gerar texto. O CLM em si foi avaliado e **adiado**:

| Ponto | CLM v0.1 | Aqui |
| --- | --- | --- |
| Codificador | Qwen3-8B inteiro servido por vLLM ou llama.cpp (~5 GB mesmo quantizado) | disputaria os 8 GB da RTX 5060 com o `qwen3:8b` da análise |
| Plataforma | Linux com NVIDIA | Windows (só via WSL2, mais uma peça) |
| Contexto | calibrado de 2K a 8K; exemplo com 2 048 tokens | descrições de vaga passam disso |
| Idioma | sem afirmação multilíngue | vagas em português e inglês |
| Treino | referência com ~1 milhão de trajetórias | teremos centenas de marcações |
| Maturidade | repositório criado em 23/09/2026 | — |

Revisitar o CLM se ele ganhar suporte multilíngue, contexto maior e um codificador
menor. Este card aplica o mesmo padrão com peças que cabem no hardware.

## Escopo

- **Conjunto de treino:** as marcações atuais do F17-01 (uma por vaga, a mais recente),
  com o vetor da vaga (F16-09) como entrada e `relevant` como alvo. Só vagas cujo vetor é
  do modelo de embedding configurado.
- **Modelo:** regressão logística com regularização (scikit-learn ou implementação
  própria em NumPy), sobre o vetor de 1 024 posições. Nada de rede neural: o volume de
  dados não sustenta.
- **Mínimo para treinar:** 60 marcações, com pelo menos 20 de cada classe. Abaixo disso, o
  modelo não é treinado e a Inbox mostra por que ("marque mais N vagas").
- **Avaliação honesta:** validação cruzada de 5 partes; relatório com AUC, precisão nas 50
  primeiras e calibração (a probabilidade de 0,8 acerta cerca de 80% das vezes?).
- **Versão do modelo:** tabela `dashboard.relevance_model` (versão, data, número de
  exemplos, métricas da validação, modelo de embedding usado, pesos serializados).
  Treinar de novo cria outra versão; a Inbox usa a mais recente que passou no gate.
- **Treino:** `make train-relevance` e um job semanal opcional, desligado por padrão
  (`WORKER_RELEVANCE_TRAIN_ENABLED`).
- **Pontuação:** `relevance_probability` calculada para as vagas com vetor, gravada com a
  versão do modelo que a produziu, e refeita quando o modelo ou o vetor mudam.
- **Inbox:** ordem "provável interesse" como opção ao lado de "score" e "recentes", e a
  probabilidade exibida como "72% de chance de interessar", com a versão do modelo no
  detalhe. Vaga sem vetor ou sem modelo treinado mostra "sem estimativa".
- **Gate:** o modelo só vira ordem disponível na Inbox se, na validação cruzada, a
  precisão das 50 primeiras ordenadas por ele superar a da ordem padrão atual. O
  relatório fica em `docs/pesquisas/`.
- **Uso secundário (Choice):** com o F17-02 pronto, a mesma técnica pode sugerir a área
  de vagas `UNKNOWN`, treinada nas áreas já classificadas pela regra. Sugestão exibida
  para o operador confirmar; nunca grava `role_family` sozinha.

## Fora de escopo

- Usar a probabilidade no score, na elegibilidade ou no veredito do matching.
- Descartar ou esconder vagas por probabilidade baixa: é ordenação, não filtro.
- Adotar o CLM, vLLM ou um segundo modelo de 8B.
- Aprender com cliques ou tempo de leitura: só marcação explícita.

## Notas de implementação

- A marcação guarda a versão do perfil (F17-01). Treinar só com marcações do perfil ativo
  ou de versões próximas; misturar gostos de perfis muito diferentes ensina ruído. Na
  primeira versão, usar todas e registrar a distribuição por versão de perfil no relatório.
- Classes desbalanceadas (o operador marca mais "não é para mim") pedem peso por classe
  na regressão.
- Pesos de 1 024 posições + intercepto cabem num JSON pequeno; não precisa de arquivo
  externo nem de pickle, o que evita carregar código de terceiros.
- A pontuação é um produto escalar por vaga: roda no worker em lote, sem GPU.

## Critérios de aceite

- [ ] Com marcações suficientes, `make train-relevance` treina, avalia e grava uma versão
      com métricas.
- [ ] Com marcações insuficientes, nada é treinado e a tela diz quantas faltam.
- [ ] Cada vaga com vetor tem a probabilidade e a versão do modelo que a produziu.
- [ ] A Inbox oferece "provável interesse" só quando o modelo passou no gate.
- [ ] Nenhuma decisão do matching muda por causa da probabilidade.
- [ ] O relatório de avaliação está em `docs/pesquisas/`.

## Verificação

- **CI:** testes do treino com vetores sintéticos separáveis (o modelo aprende) e não
  separáveis (o gate recusa); teste do mínimo de marcações; teste da serialização dos
  pesos; teste de integração da ordenação na Inbox com probabilidades fixas.
- **Máquina de referência:** o relatório com as marcações reais do operador, anexado ao PR.

## Arquivos prováveis

- `src/opportunity_radar/dashboard/relevance.py` (novo)
- `migrations/versions/*_relevance_model.py`
- `src/opportunity_radar/worker.py`, `Makefile`
- `src/opportunity_radar/dashboard/queries.py`, `presentation/http/dashboard.py`
- `apps/web/src/routes/InboxPage.tsx`
