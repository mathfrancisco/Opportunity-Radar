# CARD F18-03 — Coletor JobPosting público

- **Status:** Backlog
- **Fase:** 18 — Varredura produtiva
- **Depende de:** F18-02, F17-02, F17-06, F17-07
- **Bloqueia:** F18-09
- **Origem:** [SPEC 39](../../39-spec-varredura-produtiva.md), §6

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

- Ampliar para serviços distribuídos, IA remota ou coleta autenticada.
- Executar testes, migrações ou coletas reais nesta revisão documental.

## Critérios de aceite

- [ ] Objetos, listas e @graph geram itens com procedência.
- [ ] Página bloqueada/quebrada não vira sucesso vazio.
- [ ] Remoto não vira elegibilidade global por inferência.
- [ ] Probe e homologação exercitam o coletor real; implementação entra no fluxo normal.

## Verificação

- **CI:** Fixtures pt/en, múltiplas vagas, campos ausentes, schema divergente, soft-404 e persistência/normalização.
- **Máquina de referência:** Homologar pequena coorte de páginas estáticas e comparar extração com leitura manual.
- Conforme AGENTS.md, validação local depende de pedido explícito.

## Arquivos prováveis

`acquisition/jobposting.py` novo, registry/probing/proposals, normalização, SourceCreateForm e fixtures.
