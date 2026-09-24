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
- Candidatura aberta na vaga absorvida é movida para a vaga que fica, com registro no
  histórico do pipeline.

## Critérios de aceite

- [ ] Pares que atendem a regra viram candidatos, sem juntar nada sozinhos.
- [ ] Confirmar junta ocorrências e preserva procedência; recusar não sugere de novo.
- [ ] A taxa de duplicatas é medida antes e depois.

## Verificação

- **CI:** testes da detecção (dentro e fora da janela, empresas diferentes), da junção e
  da recusa; teste do sinal vetorial com vetores fixos.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/duplicates.py` (novo), `service.py`, `models.py`
- `migrations/versions/*_duplicate_candidate.py`
- `src/opportunity_radar/presentation/http/opportunities.py`
- `apps/web/src/routes/InboxPage.tsx`, `OpportunityDetailPage.tsx`
