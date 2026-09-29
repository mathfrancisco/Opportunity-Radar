# CARD F18-01 — Mapa de cobertura e rendimento

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F17-01, F17-07
- **Bloqueia:** F18-02, F18-04, F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §4

## Resultado

Cada empresa mostra se está coberta, por que não está e qual é a próxima ação. O operador mede vagas únicas úteis por custo e atraso.

## Escopo

- Estender search-metrics com funil catálogo → descoberta → homologação → habilitação → coleta completa recente, contando empresas canônicas.
- Separar cobertura cadastrada de operacional e tipos ATS sem coletor. Guardar motivo, última tentativa e próxima ação por lacuna.
- Medir requisições, bytes, erros, vagas únicas novas, suporte de julgamento, rendimento útil, frescor e atraso de processamento; sem datas confiáveis, atraso de descoberta é null.
- Atribuição multifuente separa primeira descoberta e contribuição. Marcas ausentes não são negativas; comparar coortes/janelas iguais.
- Registrar baseline de sete dias e metas/tetos antes da mudança. Recall amostral usa snapshots manuais de boards estratificados, sem prometer recall global.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Fonte habilitada falhando não conta como operacional.
- [ ] Aliases e oportunidades multifuente não inflam totais.
- [ ] Cada métrica expõe janela, denominador, suporte e null quando indisponível.
- [ ] Relatório registra baseline, lacunas acionáveis e plano de comparação.

## Verificação

- **CI:** Fixtures de fontes saudáveis/falhas, aliases, multifuente, datas ausentes e marcas parciais; endpoint e apresentação no painel.
- **Máquina de referência:** Relatório de baseline e amostra manual dos boards; não executar nesta tarefa documental.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`dashboard/metrics.py`, `dashboard/queries.py`, API de dashboard, telas de empresas/fontes, migrations de métricas quando necessário.
