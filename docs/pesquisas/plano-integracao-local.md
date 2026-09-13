# Plano de integração local das fontes

## Escopo da entrega e escolha inicial

Esta pesquisa fornece o cadastro de fontes e o estado de evidência. Ela não implementa agendamento, scraping, aplicação a vagas nem o projeto completo de DDD. O objetivo da próxima implementação é tornar cada fonte verificável, com histórico de execução e recuperação de falhas.

Começar com os endpoints JSON confirmados de Supabase, RevenueCat, Render, WorkOS e Spotify. Eles permitem testar normalização e persistência com evidência prévia de resposta. Em paralelo de desenvolvimento, preparar o adaptador Lever para o board da CI&T, cuja listagem mostrou Brasil e homeoffice; o endpoint específico ainda precisa de validação. Priorizar relevância de localização além da facilidade técnica.

### Estado de implementação

O adaptador Ashby parametrizado por board está implementado. O importador cria
definições desabilitadas para RevenueCat, Supabase, Render e WorkOS, e a API
exige evidência confirmada, termos revisados e coletor homologado antes de
ativá-las. A validação automatizada usa fixture e transporte HTTP simulado; a
comparação controlada com cada portal real permanece como gate operacional.

O adaptador Lever também está implementado com paginação e seleção das regiões
global/UE. O importador materializa somente o endpoint confirmado do Spotify;
CI&T continua no catálogo de evidências até a homologação do site `ciandt`.

O adaptador Greenhouse consulta a Job Board API pública pelo token do board e
preserva conteúdo, departamentos, escritórios e metadados do anúncio. O board
explicitamente identificado da AssemblyAI vira uma definição desabilitada com
estado `ats_identified`; os demais indícios de Greenhouse permanecem apenas no
catálogo até que um token seja confirmado. A ativação ainda depende da revisão
dos termos e da comparação controlada com o portal real.

## Estratégia por plataforma

| Fonte | Estratégia proposta | Validação restante |
| --- | --- | --- |
| Ashby | Adaptador para public job posting API | Identificador exato do board, campos, completude e alterações |
| Greenhouse | Job Board API pública | Board token, conteúdo e reconciliação com o portal |
| Lever | Postings API | Identificador, paginação e região da instância |
| Workable, Teamtailor, Gupy e outras | Investigar interfaces públicas e HTML por fonte | Não presumir API pública sem evidência |
| Portal próprio | HTTP e parser específico; navegador quando necessário | Renderização, paginação, estabilidade e acesso permitido |

As referências de implementação são a [Job Board API do Greenhouse](https://docs.greenhouse.io/job-board.html), a [Public Job Posting API do Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api) e a [Postings API do Lever](https://github.com/lever/postings-api). Greenhouse documenta leitura pública sem autenticação nesses endpoints. A API Lever trata anúncios publicados; não é um inventário de todas as vagas internas. Não extrapolar essas propriedades para outros produtos dos fornecedores.

## Limites de domínio sugeridos

- **Company Catalog:** empresa, aliases, grupo e fontes oficiais. Recebe as tabelas revisadas em `docs/pesquisas`; o Notion não faz parte do fluxo operacional.
- **Source Collection:** conectores, agendas, execuções, tentativas e resultados brutos. Conhece ATS e HTTP; não decide aderência ao perfil.
- **Job Catalog:** identidade da vaga, versões, localidades, status e deduplicação.
- **Matching:** regras geográficas, senioridade e perfil; Ollama pode ajudar a interpretar texto, preservando a evidência original.
- **Dashboard:** revisão de fontes, pendências e oportunidades. Consulta os domínios; não contém lógica de scraping.

Essas fronteiras cabem em um monólito modular. Não há necessidade de microserviços para o MVP.

## Execução local

Docker Compose pode hospedar PostgreSQL, backend, worker e dashboard. Ollama roda em um serviço compatível com o hardware disponível ou no host. Um agendador do próprio worker basta inicialmente; uma fila distribuída só deve entrar quando concorrência e recuperação justificarem a complexidade.

Fluxo: agendador seleciona fonte habilitada, conector consulta origem, normalizador valida campos, catálogo registra alterações e matching avalia elegibilidade. A dashboard mostra sucesso, falha, quantidade e última atualização. Extração por IA não deve ser necessária para ler campos estruturados de uma API.

## Modelo mínimo para implementação

| Entidade | Campos principais |
| --- | --- |
| company | id, name, canonical_domain, group_id, created_at |
| company_alias | id, company_id, alias, provenance |
| source | id, company_id, kind, careers_url, board_url, api_url, board_token, enabled, evidence_status, reviewed_at |
| collection_run | id, source_id, started_at, finished_at, status, response_status, items_seen, error_class |
| job | id, source_id, external_id, canonical_url, title, description, employment_type, remote_scope, first_seen_at, last_seen_at, status |
| job_location | id, job_id, country, region, city, raw_text |
| job_version | id, job_id, content_hash, observed_at, normalized_payload |
| eligibility | id, job_id, profile_id, result, reasons, evidence_text, model_version, evaluated_at |

Chave única inicial de vaga: (source_id, external_id). Ausência de identificador exige uma regra explícita de URL canônica; título sozinho não é chave. Deduplicação entre fontes deve preservar os registros de origem e ligar equivalências, evitando apagar diferenças entre anúncios.

O catálogo JSON da pesquisa é uma entrada de revisão, não uma migração SQL pronta. Conservar fonte original e URL consultada; marcar fonte como habilitada somente após validação do conector. Campos opcionais nulos significam desconhecido, não ausência garantida de funcionalidade.

## Etapas e critérios de aceite

1. **Importar e revisar:** carregar 186 empresas e as candidatas escolhidas, revisar aliases e resolver Neon/Databricks e receeve/InDebted. Aceite: identidades únicas e rastreabilidade do cadastro.
2. **Homologar cinco endpoints:** executar localmente, validar esquema, campos obrigatórios e listagem completa contra o portal. Aceite: repetição sem duplicação e erro visível quando a resposta é inválida.
3. **Agendar com moderação:** começar com intervalo configurável de 12 horas, concorrência baixa por domínio e backoff para 429/5xx. Esses valores são proposta operacional, sujeitos às regras da fonte. Aceite: execução sem sobreposição e histórico de tentativas.
4. **Detectar mudanças:** usar identificadores e hashes; considerar encerramento apenas após reconciliações completas bem-sucedidas. Aceite: uma falha ou resposta parcial nunca encerra todas as vagas.
5. **Filtrar elegibilidade:** distinguir remoto global, país específico, Europa, fuso e autorização de trabalho. Preservar “desconhecido” quando o anúncio não disser. Aceite: cada classificação tem razão e trecho de evidência.
6. **Expandir por ATS:** incorporar primeiro empresas prioritárias que reutilizam adaptadores homologados. Depois tratar portais próprios e os acessos pendentes. Aceite: cada fonte nova passa pela mesma comparação e controles.

## Tratamento de falhas

Registrar timeout, HTTP 403, 404, 429, 5xx, mudança de esquema e resultado vazio separadamente. Não interpretar uma proteção de acesso como lista vazia. Redirecionamentos entre marcas abrem pendência de revisão. Navegador local pode ser necessário em fontes dinâmicas, mas não é garantia de acesso e não deve contornar autenticação ou controles de acesso.

Antes de habilitar uma coleta recorrente, revisar as condições publicadas da fonte e usar a interface disponível apropriada. Os 222 registros, reconciliados em 220 identidades de empresa, têm termos_revisados=false e coletor_local_testado=false. Isso é informação de estado do projeto, não conclusão de que a coleta é proibida.
