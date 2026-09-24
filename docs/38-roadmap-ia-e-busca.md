# Roadmap — IA local e busca de vagas

## 1. Objetivo

Duas frentes que se apoiam, cada uma com a sua SPEC:

```text
Fase 16  camada local de IA        o modelo na GPU, medido, lendo a vaga de verdade
Fase 17  busca de vagas            mais vagas relevantes, menos ruído, busca que acha
```

- [SPEC da camada de IA](36-spec-ollama.md) — Ollama 0.34.4 na RTX 5060, `qwen3:8b-q4_K_M`,
  custo medido, prompt `v2`, pgvector e embeddings, avaliação e quantização.
- [SPEC de busca](37-spec-busca.md) — cobertura (quantidade) e precisão (acurácia), da
  coleta à Inbox.

Cards de execução: [38-roadmap-ia-e-busca](38-roadmap-ia-e-busca/README.md).

## 2. Hardware de referência

Xeon E5-2680 v4 (14 núcleos, AVX2, sem AVX-512), 16 GB de RAM, RTX 5060 com 8 GB de VRAM.
A VRAM é o limite que decide modelo, quantização e janela de contexto (SPEC de IA §3.1).

## 3. Milestones

## Milestone O — IA local na GPU, medida

```text
o modelo roda inteiro na GPU, e cada análise diz quanto custou
```

F16-01, F16-02, F16-03, F16-04 e F16-13.

## Milestone P — Busca que mede e cresce com precisão

```text
o radar sabe quantas vagas relevantes encontra e quantas das mostradas servem,
e aumenta a cobertura sem piorar a Inbox
```

F17-01 a F17-05 e F16-10.

## 4. Ordem entre as fases

1. **F16-01** e **F17-01** em paralelo: GPU e medição de busca não disputam arquivo.
2. **F16-02, F16-03** (modelo e custo) e **F17-02, F17-03** (área e full-text).
3. **F17-04, F17-05**: volume, só depois da área da vaga.
4. **F16-04 a F16-08**: tempo, orçamento, avaliação, prompt `v2`, cache.
5. **F16-09, F16-10, F17-06 a F17-08**: vetores, vagas parecidas, normalização, duplicatas.
6. **F17-09 a F17-12, F16-11 a F16-13**: descoberta, coletores novos, palavras-chave,
   buscas salvas, RAG, confirmação de modelo, métricas.

## 5. Recorte explícito

Não entram: serviços de IA remotos, modelo decidindo score ou veredito, sites que
proíbem automação ou exigem login, navegador headless, fine-tuning e candidatura
automática.
