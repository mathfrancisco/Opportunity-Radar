# CARD F17-13 — Relevância aprendida a partir das marcações

- **Status:** Backlog experimental; após Milestone P
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01, F16-09
- **Bloqueia:** Nenhum
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §13.1

## Resultado

Uma ordem opcional por estimativa de interesse só entra na Inbox após melhorar
a avaliação reservada. Não altera score, veredito, visibilidade ou elegibilidade.

## Contexto

Marcações explícitas e embeddings permitem explorar uma regressão logística
regularizada. Poucos exemplos não sustentam promessa de probabilidade calibrada.
CLM, segundo modelo de 8B e treino de rede neural continuam fora deste card.

## Escopo

- Treinar com marcas atuais do perfil ativo e texto/vetor correspondente ao
  conteúdo julgado. Marca de versão antiga não rotula automaticamente texto novo.
- Mínimo exploratório: 60 marcas, 20 por classe. Isso não libera a funcionalidade.
- Separar por tempo e grupo de duplicatas, evitando vagas equivalentes nos dois
  conjuntos. Validação cruzada agrupada usa apenas o conjunto de treino.
- Gate de produto: janela posterior reservada com pelo menos 50 oportunidades
  independentes julgadas, além do treino. Comparar P@50 das duas ordens no mesmo
  universo/filtros, com suporte e intervalo de incerteza. Sem evidência suficiente,
  manter experimental. Abaixo de 50 reportar P@k, sem chamá-la P@50.
- Relatório inclui AUC quando calculável, P@k, Brier, faixas de calibração e
  distribuição por classe/fonte/idioma. Ajustar parâmetros só no treino.
- Persistir versão do perfil, hashes das marcas/split, modelo de embedding,
  configuração, pesos JSON, métricas e identidade do artefato treinado.
- Treino manual; job semanal opcional desligado por padrão. Mudança de perfil,
  vetor ou modelo invalida a pontuação; fila refaz com versão explícita.
- Inbox mostra "estimativa de interesse". Percentual de chance só após gate
  específico de calibração com suporte registrado; sem modelo: "sem estimativa".
- Rollback para ordem determinística é imediato e não perde marcações.

## Fora de escopo

- Aprender com cliques ou ausência de candidatura.
- Misturar perfis antigos para atingir mínimo de amostras.
- Sugerir área da vaga por este modelo; isso requer avaliação separada.
- Rede neural, CLM/vLLM ou alteração de matching.

## Critérios de aceite

- [ ] Modelo não é promovido apenas por atingir 60 marcas.
- [ ] Nenhuma duplicata ou dado futuro vaza para treino/avaliação.
- [ ] Comparação P@50 usa janela independente de tamanho suficiente.
- [ ] Relatório registra suporte, calibração, versões e limitações.
- [ ] Perfil/texto/vetor alterado invalida a estimativa.
- [ ] Rollback mantém busca e marcas disponíveis.

## Verificação

- **CI:** dados sintéticos testam isolamento dos conjuntos, mínimos, nulidade
  quando métrica não é calculável, versionamento, serialização e fallback.
  Não usar separabilidade sintética como evidência de qualidade no acervo.
- **Máquina de referência:** relatório reservado com marcas reais e decisão
  registrada; não executar validações locais sem pedido explícito.

## Arquivos prováveis

- `dashboard/relevance.py`, migração de modelo/pontuação, `worker.py`
- `dashboard/queries.py`, API de dashboard, `InboxPage.tsx`
