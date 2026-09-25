# CARD F20-26 — Candidato a duplicata (sem sinal vetorial)

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-01
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-08](../../38-roadmap-ia-e-busca/fase-17/f17-08-candidato-a-duplicata.md); SPEC 43 §9

## Ajustes da Fase 20

- Sem embedding nesta fase: só a regra `title_location_window` entra. Ignorar os trechos sobre sinal vetorial, cosseno e vetores fixos.
- O valor `embedding` pode ficar no enum da regra para uso futuro, sem gerador.

## Resultado

A mesma vaga anunciada em duas fontes, em dias diferentes, aparece como "possível
duplicata" para o operador confirmar ou recusar; a confirmação junta as duas, e nada é
juntado sem regra exata ou confirmação humana.

## Contexto

O fingerprint inclui o dia da publicação (`opportunities/domain.py:876`), de propósito,
para não juntar republicações antigas. O efeito colateral é que a mesma vaga, publicada
num board da empresa e numa fonte ampla em dias diferentes, vira duas oportunidades.

## Escopo

- **Tabela `opportunities.duplicate_candidate`:** par ordenado de oportunidades, regra que
  gerou (`title_location_window` ou `embedding`), pontuação, status (`PENDING`,
  `CONFIRMED`, `REJECTED`), quem decidiu e quando.
- **Detecção** depois da normalização:
  - regra exata-relaxada: mesma empresa canônica, mesmo título normalizado, mesma
    localização normalizada, publicações a até 14 dias;
  - ~~sinal vetorial (cosseno ≥ 0,95)~~ — fora da Fase 20 (SPEC 43 §9).
- **Tela:** selo "possível duplicata" na Inbox e, no detalhe, as duas vagas lado a lado
  com as diferenças destacadas e os botões "É a mesma vaga" / "São vagas diferentes".
- **Confirmar** junta as ocorrências na oportunidade mais antiga e marca a outra como
  duplicata dela, preservando procedência e avaliações. **Recusar** grava o par para não
  sugerir de novo.
- **Métrica:** taxa de duplicatas no relatório do F20-01 (antigo F17-01), antes e depois.

## Fora de escopo

- Junção automática. Uma regra aprendida por par de fontes, depois de N confirmações, é
  avaliada num card próprio com os dados deste.

## Notas de implementação

- A junção reaproveita a lógica de `MERGED` da normalização; a oportunidade absorvida não
  é apagada, ganha `duplicate_of`.
- Uma única candidatura ativa na vaga absorvida pode ser movida com histórico.
  Duas candidaturas ativas bloqueiam a junção com conflito acionável; não escolher
  uma nem encerrar outra automaticamente.

## Contrato de junção

- Confirmar exige versões esperadas de ambas as oportunidades, transação única e
  operação idempotente. Confirmar novamente retorna a mesma resolução.
- Preservar procedência, avaliações históricas, marcas e candidaturas; redirecionar
  ids absorvidos. Avaliações antigas não viram avaliações atuais da sobrevivente.
- Registrar antes/depois e ids movidos para permitir correção supervisionada.
  Conflitos de marcação ficam explícitos; não escolher silenciosamente.
- Impedir ciclos de `duplicate_of` e normalizar pares. Candidatos vetoriais exigem
  vetores atuais. Recusa é contextualizada por versão, com política para revisão
  após mudança material; não sugerir o mesmo par inalterado repetidamente.

## Critérios de aceite

- [ ] Pares que atendem a regra viram candidatos, sem juntar nada sozinhos.
- [ ] Confirmar junta ocorrências e preserva procedência; recusar não sugere de novo.
- [ ] A taxa de duplicatas é medida antes e depois.

- [ ] Duas candidaturas ativas geram conflito sem mutação parcial.
- [ ] Repetição, concorrência, ids antigos e ciclo de duplicatas têm cobertura no CI.
- [ ] Junção não perde marcas/histórico e invalida avaliações derivadas quando necessário.

## Verificação

- **CI:** testes da detecção (dentro e fora da janela, empresas diferentes), da junção e
  da recusa; teste do sinal vetorial com vetores fixos.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/duplicates.py` (novo), `service.py`, `models.py`
- `migrations/versions/*_duplicate_candidate.py`
- `src/opportunity_radar/presentation/http/opportunities.py`
- `apps/web/src/routes/InboxPage.tsx`, `OpportunityDetailPage.tsx`

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-26 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
