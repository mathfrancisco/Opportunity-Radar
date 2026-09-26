# CARD F17-08 — Candidato a duplicata entre fontes

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01 (sinal vetorial após F16-09)
- **Bloqueia:** Nenhum
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §12

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
  - com o F16-09 pronto: cosseno ≥ 0,95 na mesma empresa, para título reescrito entre
    fontes.
- **Tela:** selo "possível duplicata" na Inbox e, no detalhe, as duas vagas lado a lado
  com as diferenças destacadas e os botões "É a mesma vaga" / "São vagas diferentes".
- **Confirmar** junta as ocorrências na oportunidade mais antiga e marca a outra como
  duplicata dela, preservando procedência e avaliações. **Recusar** grava o par para não
  sugerir de novo.
- **Métrica:** taxa de duplicatas no relatório do F17-01, antes e depois.

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
