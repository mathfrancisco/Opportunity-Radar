# CARD F18-04 — Agenda por rendimento e orçamento de rede

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F18-01, F17-07
- **Bloqueia:** F18-05, F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §7

## Resultado

A coleta revisita fontes pelo frescor e rendimento, respeitando limites agregados e sem abandonar fontes pouco observadas.

## Escopo

- Estender scheduler/política existentes com next_due_at, motivo, limites min/max e custo recente; persistir cooldown por host/provedor.
- Compartilhar orçamento entre coleta, probe e descoberta. Aging e reserva inicial de 10% para exploração evitam exclusão permanente; teto de política prevalece.
- Requisições condicionais por representação/escopo com ETag/Last-Modified; validar Vary, cache-control e configuração.
- 429/503 respeitam Retry-After em segundos/data, backoff/jitter e estado após restart; falha de uma fonte não bloqueia outras.
- 304 mantém semântica de revalidação, não ausência. Até F18-05 comprovar manifest completo, não usar 304 para encerrar vaga.
- Não adaptar por falta de marcação humana; registrar plano e permitir rollback ao agendamento fixo.

## Fora de escopo

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Nenhum host excede orçamento ao combinar fontes, sondas e descoberta.
- [ ] Fonte pouco observada volta a ser visitada dentro do máximo configurado
      quando há capacidade; insuficiência de orçamento gera atraso explícito,
      sem violar limites do provedor.
- [ ] Cooldown sobrevive a reinício; Retry-After não é ignorado.
- [ ] Mesma coorte mantém cobertura/recall e reduz custo ou atraso medido.

## Verificação

- **CI:** Relógio controlado: concorrência por host, fairness, cooldown/restart, 304, validadores incompatíveis e rollback.
- **Máquina de referência:** Comparação de sete dias antes/depois com requisições, bytes, frescor e cobertura sob mesmos tetos.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`acquisition/scheduling.py`, política HTTP dos coletores, worker e migrations de estado de host/representação.
