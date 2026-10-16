# F53 — evidência Cloudflare de 15/10

Data da consulta: 2026-10-15 (America/Sao_Paulo). O coordenador acessou o
dashboard Cloudflare em modo de leitura. Não alterou configurações, registros
DNS, variáveis, plano ou implantação. Nenhum e-mail, ID de conta ou valor de
segredo foi registrado.

## Zona e plano Workers

- A zona `livechat.tech` aparece com status Ativo, plano Free e DNS indicado
  como completo; nenhum Worker está conectado. Ela não foi aprovada para o
  Radar e esses estados não comprovam posse/controle atual nem registros DNS
  do Radar. O usuário não autorizou seu uso e informou que o site antigo está
  fora do ar; isso não permite concluir se o domínio expirou.
- A lista Registrar da conta mostrava “Nenhum domínio registrado na Cloudflare
  ainda”. Isso não prova que `livechat.tech` expirou, que não está registrado
  em outro registrar ou que a conta não tenha controle externo. Não comprar,
  registrar nem renovar domínio; o domínio aprovado para o Radar permanece
  indefinido e nenhuma configuração foi alterada.
- O painel Workers mostrava Free, US$ 0. O botão desabilitado “Plano atual”
  indicava que esse plano estava selecionado; não indicava serviço ou plano
  desativado. Para 1–15/10, mostrava 35 de 3.000 minutos de build, zero requests
  no dia da consulta e quota de 100.000 requests por dia.
- Esses dados descrevem o plano e os contadores Workers exibidos. Não provam
  custo total zero, ausência de cobrança/overage, plano de outros produtos nem
  quota suficiente para uso futuro. Nenhum upgrade foi selecionado.

## Domínio e URL de piloto

Cloudflare documenta `workers.dev` como subdomínio gratuito voltado a projetos
de hobby/pessoais. Essa opção pode servir como URL de piloto sem compra de
domínio, mas não comprova atendimento aos critérios de produção do F53-02/08.
O guia Clerk de produção exige domínio que o proprietário controle; a conta
não mostrou domínio registrado na Cloudflare e nenhum domínio foi aprovado
para o Radar. Portanto, `workers.dev` não substitui o domínio próprio/controle
exigido por Clerk em produção, nem o critério Cloudflare Pages AC01 do F53-08
([workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/),
[Clerk em produção](https://clerk.com/docs/guides/development/deployment/production)).

## Worker e build conectado ao GitHub

O dashboard mostrava o Worker `opportunity-radar`, de assets estáticos, com
100% do tráfego na versão `6d7acd52`. O build era
`f5b29fdc-45ab-43c1-9c29-11bff7919d38`, da branch `main`, commit
`02327963bf86aa76e7b3be16ef69b69e827bcadf`. A URL pública
[`opportunity-radar.math-francisco2.workers.dev`](https://opportunity-radar.math-francisco2.workers.dev/)
respondeu por HTTPS e mostrou a tela de falha fechada:
`Configuração de autenticação ausente` e
`Defina VITE_CLERK_PUBLISHABLE_KEY`.

As configurações de build exibiam:

| Item | Valor observado |
| --- | --- |
| Repositório e diretório raiz | Repositório Opportunity Radar, `apps/web` |
| Branch | `main` |
| Comando de build | `npm ci && npm run build` |
| Comando de publicação | `npx wrangler deploy` |
| Builds automáticos | Ativados |
| Variáveis e secrets de build | Nenhum configurado |
| Domínios customizados, rotas ou bindings | Nenhum configurado |

Isso é um Worker conectado diretamente ao GitHub, não um projeto Cloudflare
Pages. O [critério F53-08 AC01](../cards/f53-08-clerk-pages-frontend.md) exige
que Pages construa em `apps/web` e publique `dist`; a implantação observada não
satisfaz esse critério por equivalência presumida. A divergência precisa de
decisão e avaliação explícitas antes de mudar a estratégia do card.

## Configuração da aplicação

O frontend lê `VITE_CLERK_PUBLISHABLE_KEY` em
[`main.tsx`](../../../apps/web/src/main.tsx#L6-L9); sem valor, ele não inicia
autenticação e apresenta a tela observada. No `.env.local` da raiz, essa chave
está classificada como `pk_test_`; `VITE_API_BASE_URL` está ausente. Nenhum
valor foi incluído nesta evidência. A chave local de teste não configura o
build Cloudflare nem comprova uma instância Clerk de produção.

[`api.ts`](../../../apps/web/src/lib/api.ts#L1-L2) usa `/api` quando
`VITE_API_BASE_URL` não está definida. O Worker configurado em
[`wrangler.jsonc`](../../../apps/web/wrangler.jsonc#L1-L10) publica apenas
assets estáticos e não declara API route, proxy ou binding. Não há evidência de
uma API implantada ou roteada por esse Worker; portanto, resolver a chave Clerk
isoladamente não comprova que o aplicativo pode autenticar chamadas à API.

## Gate de publicação

O workflow GitHub bloqueia a publicação de imagens GHCR antes do passo de build
enquanto `TENANCY_OWNER_API_READY` não estiver habilitada. O checkout contém
código relacionado à tenancy em [`profile.py`](../../../src/opportunity_radar/presentation/http/profile.py),
[`pipeline.py`](../../../src/opportunity_radar/presentation/http/pipeline.py) e
[`dashboard.py`](../../../src/opportunity_radar/presentation/http/dashboard.py),
além do teste de dois usuários
[`test_auth_tenancy_integration.py`](../../../tests/backend/http/test_auth_tenancy_integration.py).
A presença desses arquivos não comprova integração aceita, aprovação dos
testes nem revisão independente; esses resultados ainda precisam ser
registrados. A implantação Worker conectada ao GitHub segue um caminho
separado e não passa pelo gate GHCR. A especificação determina que caminhos
alternativos de publicação também permaneçam operacionalmente bloqueados até
os mesmos critérios serem aceitos
([gate de tenancy](../../superpowers/specs/2026-10-08-owner-tenancy-release-gate.md#L9-L17)).

Assim, não alterar as variáveis do build nem disparar novo deploy de produção
para remover a tela de erro enquanto esse gate estiver aberto. Esta consulta
não alterou o Worker nem liberou o gate. Resultados de CI citados na matriz
continuam históricos; não foram reexecutados nesta verificação.
