# CARD F20-32 — Coletor Gupy

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-27, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-10](../../38-roadmap-ia-e-busca/fase-17/f17-10-coletores-novos.md)

## Ajustes da Fase 20

- Este card é o sub-card de **Gupy** do F17-10. Aplicar o escopo e os critérios abaixo só a Gupy.
- A revisão de termos vem primeiro; se o endpoint proíbe automação, o card fecha como "não viável" com a revisão registrada.
- A ordem entre os cinco coletores segue o relatório do F20-27 e o mapa do F20-35; a numeração não é prioridade.

## Resultado

Os ATS que mais destravam empresas do catálogo ganham coletor, um de cada vez, na ordem
que a descoberta do F20-27 (antigo F17-09) medir, cada um com termos revisados antes de ser escrito.

## Contexto

Hoje o catálogo tem 12 empresas em ATS sem coletor: Workday 4, Teamtailor 3, Workable 2,
Factorial 2, Gupy 1. O F20-27 (antigo F17-09) deve aumentar esses números. Gupy, com pouca presença no
catálogo, é muito usado no mercado brasileiro e pode subir na ordem depois da descoberta.

## Escopo

Este card é um guarda-chuva: **cada ATS vira um sub-card próprio** (F17-10a, F17-10b, …)
quando for iniciado, na ordem do relatório do F20-27 (antigo F17-09). Cada sub-card entrega:

1. **Revisão de termos** do endpoint público, registrada em `docs/pesquisas/` antes de
   qualquer código. Endpoint que proíbe acesso automatizado encerra o sub-card.
2. **Coletor** com a interface dos atuais: `source_type`, `CollectorCapabilities`,
   `discover`, telemetria, política de rede, retentativa, validador de chave.
3. **Board falso** em `tests/e2e/` ou fixture equivalente, com paginação e erro.
4. **Integração** com o resto da Fase 14: `PROBE_TYPES` da sonda, `IDENTIFIER_KEYS` das
   propostas, padrões de chave do F20-03 (antigo F17-04) e assinaturas do F20-27 (antigo F17-09), `SUPPORTED_ATS` do
   cadastro de empresa, formulário de criação de fonte.
5. **Mapeamento** de departamento (F20-03 (antigo F17-02)) e senioridade (F20-02 (antigo F17-06)) só para campos que o
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

- A ordem sai do relatório do F20-27 (antigo F17-09)/F20-35 (antigo F18-01): empresas canônicas desbloqueadas,
  vagas únicas úteis, custo de integração/manutenção e disponibilidade do endpoint.
  Quantidade de empresas é hipótese de rendimento, não garantia.
- Paginação, detalhe ausente, 429/Retry-After, duplicatas entre páginas e mudança
  de schema entram no contrato de cada coletor; falha nunca parece board vazio.
- Coletor novo só é habilitado depois do F20-03 (antigo F17-02), pela mesma razão do F20-25 (antigo F17-05).

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
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-32 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
