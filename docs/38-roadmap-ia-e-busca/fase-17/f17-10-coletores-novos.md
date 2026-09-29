# CARD F17-10 — Coletores novos, na ordem medida

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-09, F17-02, F17-06, F17-07
- **Bloqueia:** Nenhum; expansão após Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §6

## Resultado

Os ATS que mais destravam empresas do catálogo ganham coletor, um de cada vez, na ordem
que a descoberta do F17-09 medir, cada um com termos revisados antes de ser escrito.

## Contexto

Hoje o catálogo tem 12 empresas em ATS sem coletor: Workday 4, Teamtailor 3, Workable 2,
Factorial 2, Gupy 1. O F17-09 deve aumentar esses números. Gupy, com pouca presença no
catálogo, é muito usado no mercado brasileiro e pode subir na ordem depois da descoberta.

## Escopo

Este card é um guarda-chuva: **cada ATS vira um sub-card próprio** (F17-10a, F17-10b, …)
quando for iniciado, na ordem do relatório do F17-09. Cada sub-card entrega:

1. **Revisão de termos** do endpoint público, registrada em `docs/pesquisas/` antes de
   qualquer código. Endpoint que proíbe acesso automatizado encerra o sub-card.
2. **Coletor** com a interface dos atuais: `source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa, validador de chave.
3. **Board falso** em `tests/e2e/` ou fixture equivalente, com paginação e erro.
4. **Integração** com o resto da Fase 14: `PROBE_TYPES` da sonda, `IDENTIFIER_KEYS` das
   propostas, padrões de chave do F17-04 e assinaturas do F17-09, `SUPPORTED_ATS` do
   cadastro de empresa, formulário de criação de fonte.
5. **Mapeamento** de departamento (F17-02) e senioridade (F17-06) só para campos que o
   endpoint realmente expõe.

Endpoints candidatos, **a confirmar na revisão de termos** (não são fato até lá):

| ATS | Forma provável do endpoint público |
| --- | --- |
| Workday | busca JSON por tenant e site (`/wday/cxs/<tenant>/<site>/jobs`), paginada, com detalhe por vaga |
| Teamtailor | página pública de vagas por empresa, com feed |
| Workable | widget público por conta |
| Factorial | página pública de vagas por empresa |
| Gupy | portal público de vagas por empresa |

## Fora de escopo

- Qualquer fonte que exija login ou proíba automação.
- Coletar por raspagem de HTML quando existe endpoint estruturado.

## Notas de implementação

- A ordem sai do relatório do F17-09/F18-01: empresas canônicas desbloqueadas,
  vagas únicas úteis, custo de integração/manutenção e disponibilidade do endpoint.
  Quantidade de empresas é hipótese de rendimento, não garantia.
- Paginação, detalhe ausente, 429/Retry-After, duplicatas entre páginas e mudança
  de schema entram no contrato de cada coletor; falha nunca parece board vazio.
- Coletor novo só é habilitado depois do F17-02, pela mesma razão do F17-05.

## Critérios de aceite (por sub-card)

- [ ] Termos revisados e registrados antes do código.
- [ ] Coletor com teste contra board falso, incluindo paginação e erro.
- [ ] Sonda, proposta, cadastro e formulário reconhecem o ATS.
- [ ] Pelo menos uma empresa real do catálogo homologada e coletando.

## Verificação

- **CI:** testes do coletor contra o board falso; teste de integração da sonda com o tipo
  novo.
- **Máquina de referência:** primeira coleta real registrada no PR do sub-card.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/<ats>.py` (novo por sub-card)
- `src/opportunity_radar/acquisition/registry.py`, `probing.py`, `proposals.py`
- `src/opportunity_radar/companies/registration.py`
- `apps/web/src/components/SourceCreateForm.tsx`
- `tests/backend/acquisition/`, `tests/e2e/`
