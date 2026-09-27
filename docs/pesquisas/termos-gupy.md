# Revisão de termos — Gupy (F20-32)

**Data:** 2026-09-27
**Card:** [F20-32 — Coletor Gupy](../44-roadmap-fase-20/fase-20/f20-32-coletor-gupy.md)
**Decisão:** **não viável.** Os Termos de Uso da Gupy proíbem explicitamente agregar,
copiar ou duplicar vagas da plataforma — exatamente a operação de um coletor. O sub-card
fecha aqui, sem código, conforme a seção "Ajustes da Fase 20" do card ("se o endpoint
proíbe automação, o card fecha como 'não viável' com a revisão registrada") e a regra
geral do F17-10 ("Endpoint que proíbe acesso automatizado encerra o sub-card").

## O que existe (para registro, mesmo não sendo usado)

Toda empresa que usa Gupy tem uma página pública de vagas em um subdomínio
(`https://<empresa>.gupy.io/`, ex.: `https://asaas.gupy.io/`). A página é renderizada no
servidor (Next.js) e embute o payload de hidratação em um bloco
`<script id="__NEXT_DATA__" type="application/json">` no HTML: dentro dele, em
`props.pageProps`, está a lista de vagas ativas da empresa em um único carregamento — sem
paginação real por parâmetro de URL (a paginação visível na UI é só do lado do cliente
sobre a lista já carregada). Cada item traz `id`, `title`, `type`, `department`,
`workplace` (endereço e `workplaceType`) e `quickApply`, mas não a descrição completa —
essa só aparece na página de detalhe (`https://<empresa>.gupy.io/job/<id>`, também SSR,
mesmo padrão `__NEXT_DATA__`).

Não há endpoint JSON público e estruturado dedicado por empresa (ao contrário de
Workday/Teamtailor/Workable/Factorial): a única API JSON encontrada
(`https://employability-portal.gupy.io/api/v1/jobs?...`) é o buscador agregado do portal
de vagas da própria Gupy (`portal.gupy.io`), que mistura vagas de todos os clientes Gupy
por palavra-chave — não filtra por empresa de forma direta e não é o mecanismo que a
página pública de uma empresa usa. Coletar por empresa exigiria extrair o JSON do
`__NEXT_DATA__` embutido no HTML da página — uma forma de raspagem, ainda que de um bloco
JSON, não de nós de DOM/CSS —, o que o card já lista como fora de escopo quando existe
alternativa mais limpa; aqui nem chega a existir uma API JSON por empresa para comparar.

## robots.txt (verificado)

`https://asaas.gupy.io/robots.txt` (mesmo formato observado em outras contas):

```
User-agent: *
Allow: /
Disallow: /companies
Disallow: /candidates

Sitemap: https://job-boards.api.gupy.io/production/job-board-content?jobBoardName=google&subdomain=asaas
```

`Disallow` não bloqueia `/` (a página de vagas) nem `/job/<id>` (detalhe da vaga) — pelo
robots.txt isoladamente, a leitura seria permitida. Isso por si só não decide a
viabilidade: os Termos de Uso, abaixo, proíbem a operação por outro caminho.

## Termos de Uso da Gupy (decisivo)

**Termos de Uso da Plataforma de Recrutamento e Seleção — Candidatos**
(`gupy.io/termos-de-uso-recrutamento-e-selecao-candidatos`, verificado nas versões PT e EN
em 2026-09-27). Na seção de diretrizes gerais de uso ("Diretrizes Gerais do Usuário"),
cláusula de proibições:

> "É proibido para o Candidato Pessoa Física (e Usuários em geral, conforme aplicável):
> [...] agregar, copiar ou duplicar partes do Gupy Recrutamento e Seleção, incluindo
> oportunidades de trabalho expiradas; [...]"

(versão EN, mesmo documento: *"It is prohibited for the Candidate Individual (and Users
in general as applicable): [...] aggregate, copy, or duplicate parts of Gupy Recruitment
and Selection, including expired job opportunities; [...]"*)

Esta cláusula:

- se aplica a "Usuários em geral" — não só a candidatos com conta —, e o texto do próprio
  documento trata a página pública de vagas (o que o candidato vê e navega) como parte do
  "Gupy Recrutamento e Seleção", o produto inteiro, não um sistema separado;
- proíbe nominalmente **agregar, copiar ou duplicar** vagas, **incluindo vagas expiradas**
  — a descrição exata da função de um coletor: ler o board, guardar as vagas na base do
  produto e manter histórico mesmo após a vaga sair do ar;
- é uma proibição específica e nomeada, diferente da cláusula genérica de "não prejudicar
  a operação do serviço" que Workday/Teamtailor/Workable/Factorial tinham (e que, na
  ausência de cláusula específica, foi lida como não bloqueando um coletor de baixa
  frequência e sem autenticação — ver `docs/pesquisas/termos-workday.md`,
  `termos-teamtailor.md`, `termos-workable.md`, `termos-factorial.md`). Aqui há cláusula
  nomeada para exatamente esta operação.

Não foi encontrada, nos termos de Empresas
(`gupy.io/termos-de-uso-recrutamento-e-selecao-empresas`) nem no aviso de privacidade para
sites (`gupy.io/aviso-de-privacidade-site`), qualquer permissão explícita que afaste essa
proibição para terceiros que agregam vagas publicadas por clientes Gupy.

## Taxa, atribuição

Não avaliado — a decisão já é negativa pelos Termos de Uso, então não há política de rede
nem atribuição a definir para um coletor que não será escrito.

## Decisão

**Não viável.** Diferente de Workday, Teamtailor, Workable e Factorial — onde a zona era
"endpoint público, sem termo dedicado, só cláusula genérica" —, a Gupy tem cláusula
nomeada nos seus próprios Termos de Uso proibindo agregar/copiar/duplicar vagas, aplicável
a "Usuários em geral". O card F20-32 fecha aqui: nenhum código de coletor, teste, registro
em `registry.py`/`probing.py`/`proposals.py`/`registration.py`, nem alteração em
`apps/web`, foi escrito. `"gupy"` permanece fora de `SUPPORTED_ATS` e `PROBE_TYPES`.
Nenhuma chamada foi feita a boards reais de empresas do catálogo além das duas
verificações de `robots.txt`/termos acima (não são coleta de vagas, só leitura de
política pública).

## Referências

- https://asaas.gupy.io/robots.txt (verificado, `Disallow` não cobre `/` nem `/job/`)
- https://www.gupy.io/en/termos-de-uso-recrutamento-e-selecao-candidatos (verificado,
  cláusula de proibição de agregação/cópia)
- https://www.gupy.io/termos-de-uso-recrutamento-e-selecao-candidatos (mesma cláusula, PT)
- `https://employability-portal.gupy.io/api/v1/jobs?jobName=&offset=0&limit=10` (chamada
  manual isolada, fora de CI, só para confirmar que é o buscador agregado do portal
  `portal.gupy.io`, não um endpoint por empresa)
- Estrutura SSR (`__NEXT_DATA__`) observada em `https://asaas.gupy.io/` (chamada manual
  isolada, fora de CI), registrada aqui só para documentar por que não há endpoint JSON
  estruturado por empresa — não usada em código, já que a decisão de viabilidade é
  negativa antes dessa etapa.
