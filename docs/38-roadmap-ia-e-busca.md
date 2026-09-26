# Roadmap — IA local, busca e varredura produtiva

> **Consolidado na [Fase 20](44-roadmap-fase-20/README.md).** O status oficial destes cards passa a ser o da Fase 20
> ([SPEC 43](43-spec-llm-cloud-e-consolidacao.md)). Os cards abaixo seguem como referência de escopo.

## 1. Objetivo

Encontrar oportunidades únicas, abertas e relevantes nos sites de interesse,
com rastreabilidade, baixo atraso e custo controlado de coleta e análise local.

- [SPEC 36 — IA](36-spec-ollama.md): contexto, qualidade, cache e recursos locais.
- [SPEC 37 — Busca](37-spec-busca.md): cobertura, precisão e consulta na Inbox.
- [SPEC 39 — Varredura produtiva](39-spec-varredura-produtiva.md): descoberta
  limitada, páginas públicas, delta, agenda e utilidade por custo.

[Cards 16/17](38-roadmap-ia-e-busca/README.md) e
[cards 18](40-roadmap-varredura-produtiva/README.md).

## 2. Hardware de referência

Xeon E5-2680 v4, 16 GB de RAM e RTX 5060 com 8 GB de VRAM.
Medir análise e embedding juntos; a busca textual não depende de GPU.

## 3. Milestones

### Milestone O — IA local medida

F16-01 a F16-04 e F16-13. Parte da implementação está integrada; os cards
distinguem isso de aceite com medição real. Não marcar Done só pelo merge.

### Milestone P — Busca confiável e cobertura básica

F17-01 a F17-07: medição, área, full-text, propostas/homologação, normalização
retroativa e completude/encerramento. A coleta parcial não aparenta sucesso vazio.
F16-10 não bloqueia esse marco; é opção posterior condicionada ao ganho medido.

### Milestone Q — Varredura produtiva

F18-01 a F18-09: mapa de lacunas, descoberta limitada, JobPosting, orçamento
de rede, delta/presença, IA útil e prova de integridade/recuperação.
RAG e relevância aprendida não bloqueiam esse marco.

## 4. Ordem de execução

1. F18-07/08: preservar perfil e tornar backup verificável durante operação.
   F17-01 e F17-07 podem começar em paralelo.
2. F17-02/06/03: área, renormalização confiável e full-text. F17-04 pode propor
   fontes antes, mas habilitação em massa espera F17-02/07.
3. F17-05: homologação; F16-05/06/07/08: contexto, avaliação reservada e cache.
   Atualizar contratos já implementados conforme os reforços dos cards.
4. F18-01 e F17-09 → F18-02: medir lacunas e ampliar descoberta. F17-10 e
   F18-03 ampliam coletores conforme rendimento, com normalização/completude prontas.
5. F18-04/05: orçamento por host e coleta incremental; F17-08/11/12: identidade,
   rotação de consultas e buscas salvas, observando suas dependências.
6. F18-06/09: IA seletiva, prova pela interface e relatório de produtividade.
7. F16-09/10 podem evoluir após seus pré-requisitos, sem atrasar full-text.
   F16-11 e F17-13 são experimentos opcionais após os marcos básicos; F16-12
   confirma modelo com evidência, sem bloquear o ganho de cobertura.

A numeração identifica trabalho, não impõe esperar a fase inteira anterior.
Dependências detalhadas nos cards prevalecem sobre paralelismo ilustrativo.

## 5. Recorte explícito

Não entram serviços de IA remotos, modelo decidindo score/veredito, fontes que
proíbem automação ou exigem login, navegador headless, fine-tuning ou candidatura
automática. Sites públicos estáticos homologados entram pela SPEC 39.
