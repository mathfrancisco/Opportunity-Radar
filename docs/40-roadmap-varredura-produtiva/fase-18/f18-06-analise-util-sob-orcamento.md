# CARD F18-06 — Análise útil com IA sob orçamento

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F18-05, F16-07, F16-08
- **Bloqueia:** F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §9

## Resultado

A IA ajuda a decidir sobre vagas novas/alteradas e lacunas relevantes com evidência, dentro da capacidade local.

## Escopo

- Usar identidade completa e reuso F16-08; mesma vaga sem mudança não paga nova inferência.
- Priorizar recomendadas/alta prioridade e revisão com lacuna; aging e amostra de elegíveis pouco priorizadas avaliam perdas do funil.
- Orçamentos configuráveis de chamadas, tokens e tempo por ciclo/dia. Limite adia com motivo e registra custo de falhas.
- Sugestões de campo ficam separadas do canônico; aplicar exige revisão, trecho/origem e correção versionada. IA não muda score nem navega.
- Medir riscos/lacunas confirmados, falsos alertas, custo por análise útil e tempo humano por amostra. Não tratar clique ou ausência de candidatura como relevância.
- Rollback da política mantém análises históricas; sem Ollama, coleta/matching/Inbox continuam.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Revisita sem mudança não chama IA; alteração material invalida reuso.
- [ ] Budget adia sem perder oportunidade nem bloquear o worker.
- [ ] Sugestão não altera campo/matching antes da confirmação.
- [ ] Relatório compara fila atual e política nova com suporte e custo/qualidade.

## Verificação

- **CI:** Adaptador contador, clock controlado, budget, aging, indisponibilidade e confirmação concorrente com expected_version.
- **Máquina de referência:** Amostra estratificada julgada pelo operador e carga real combinada; efeito sem suporte é inconclusivo.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`matching/service.py`, repository, worker, métricas e painel de análise; esquema separado de sugestões/correções.
