# F50-12 — Duplicatas pendentes e normalizações em revisão

- **Data:** 2026-10-05
- **Card:** F50-12, itens 2 e 3, da [SPEC 50](../50-spec-motor-de-busca.md)
- **Base:** Postgres da stack `spec46full`, sessão somente leitura, com a API e o worker
  parados. As classificações abaixo vêm de comparação de texto e de identificadores, não de
  rótulo humano.

## 1. Duplicatas `title_location_window`

**Regra** (`opportunities/duplicates.py:76-146`): empresa, título e localização normalizados
iguais, e `published_at` com até 14 dias de diferença. Não olha descrição, fonte, identificador
externo nem URL.

**Medição:** 108 candidatos em `PENDING` (a spec contava 107).

| Categoria | Pares |
|---|---|
| Mesma empresa, mesmo título, descrição idêntica | 105 |
| Mesma empresa, mesmo título, descrição diferente | 2 |
| Outra (título difere só em pontuação) | 1 |
| Empresas diferentes | 0 |

- Os 108 pares vêm da mesma fonte, e nenhum compartilha identificador externo.
- 95 são de Workday: Santander 37, NVIDIA 36, Abbott 12.
- Nos pares de descrição idêntica, os identificadores são requisições distintas (por exemplo
  `_R-059329` e `_R-059055`). É a mesma vaga aberta em várias requisições, não uma
  republicação.

**Taxa de acerto:** 0 de 108 pares parece ser a mesma vaga republicada. Com esta amostra, o
limite superior de 95% fica perto de 3%.

**Recomendação:** a regra não deve confirmar sozinha. Descrição idêntica, mesma fonte e
janela de datas não separam republicação de requisições múltiplas. Uma condição possível
seria identificadores que diferem só por sufixo de republicação, mas a amostra não tem nenhum
exemplo positivo para validá-la.

**Decisão pendente do dono:** manter os pares como pendência manual, ou tratar requisições
múltiplas da mesma vaga como um grupo no Inbox. A segunda opção é mudança de produto, fora
desta spec.

## 2. Normalizações em `REVIEW_REQUIRED`

A spec atribuía quase todas as 4.809 a `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`. A medição
mostra outra distribuição:

| Motivo | Linhas |
|---|---|
| `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY` | 4.367 |
| `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED` | 503 |
| `EXACT_VERSIONED_FINGERPRINT` | 12 |
| `IDENTITY_REFRESHED_SAME_EXTERNAL_ID` | 4 |

**Condição do motivo medido** (`opportunities/service.py:194-228`): o mesmo identificador
externo na mesma fonte chega com identidade diferente, e outra vaga já é dona da identidade
nova. Sem essa colisão, a mudança é aceita em silêncio.

**O que as 503 mostram:**

- Duas fontes concentram 447 (89%): Nubank 257 e CI&T 190.
- 484 foram processadas em 2026-09-29. Depois da lógica de atualização de 2026-10-04, 4.825
  mudanças de identidade foram aceitas com `SUCCEEDED`. As 503 são, na maior parte, resíduo de
  uma data, não um fluxo contínuo.
- O título do payload novo é igual ao da vaga em 473 casos e diferente em 30 (6%). Nos
  diferentes há mudança real, por exemplo "AI Engineer Agentic SDLC" para "Senior AI Engineer
  Agentic SDLC".

**O que não foi possível determinar:** em 48 dos 50 casos amostrados, a vaga concorrente não
pôde ser identificada. A identidade do candidato não é gravada e a vaga nova não chega a ser
criada. Título, localização e dia batem com o payload, então o componente que muda deve ser
modo de trabalho, tipo de contrato ou empresa. Sem a concorrente, não dá para afirmar se a
colisão é a mesma vaga.

**Recomendação:**

- Os 473 casos de título igual parecem efeito de recoleta, mas aceitar em lote só é seguro
  depois de conferir a vaga concorrente. Para isso, o motivo precisa gravar o identificador da
  concorrente, o que hoje não faz.
- Os 30 casos de título diferente ficam em revisão.

**Fora desta medição:** as 4.367 linhas de `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`, que
são o grosso da fila e seguem outro caminho (`service.py:273-287`). Elas carregam
`candidate_opportunity_ids`, então são mensuráveis. Dado o resultado do §1, é provável que
sejam o mesmo fenômeno de requisições múltiplas, mas isso não foi medido.
