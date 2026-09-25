# CARD F20-37 — Coletor JobPosting público

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** D — Varredura produtiva
- **Depende de:** F20-36, F20-03
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-03](../../40-roadmap-varredura-produtiva/fase-18/f18-03-coletor-jobposting-publico.md); [SPEC 39](../../39-spec-varredura-produtiva.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Dependências antigas de F17 foram fechadas por F20-01 a F20-03.

## Resultado

Páginas públicas sem ATS suportado entram no radar pelo mesmo contrato e com evidência de cada campo.

## Escopo

- Homologar source_type jobposting, probe, registro e formulário; preferir API/feed existente antes de HTML.
- Extrair JSON-LD JobPosting em objeto/lista/@graph; validar identidade, empresa, título, descrição e link de candidatura.
- Separar local, residência permitida, trabalho remoto, visto, salário/moeda/período e validade. Ausência é UNKNOWN.
- HTML sem JSON-LD só com mapeamento versionado específico e fixture; sem headless ou seletores adivinhados.
- Challenge, soft-404, estrutura alterada e conflito entre texto/marcação são falha/revisão. Detalhe individual não prova board completo.
- Produzir SourceRun/RawItem; ausência em sitemap ou validThrough vencido não fecha oportunidade global automaticamente.

## Fora de escopo

- Ampliar para serviços distribuídos ou coleta autenticada. A IA remota agora é o Groq, definido na SPEC 43.
- Executar coletas reais no CI.

## Critérios de aceite

- [ ] Objetos, listas e @graph geram itens com procedência.
- [ ] Página bloqueada/quebrada não vira sucesso vazio.
- [ ] Remoto não vira elegibilidade global por inferência.
- [ ] Probe e homologação exercitam o coletor real; implementação entra no fluxo normal.

## Verificação

- **CI:** Fixtures pt/en, múltiplas vagas, campos ausentes, schema divergente, soft-404 e persistência/normalização.
- **Máquina de referência:** Homologar pequena coorte de páginas estáticas e comparar extração com leitura manual.
- Conforme o `AGENTS.md`, a validação repetível vive no `.github/workflows/pipeline.yml`.

## Arquivos prováveis

`acquisition/jobposting.py` novo, registry/probing/proposals, normalização, SourceCreateForm e fixtures.

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
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-37 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
