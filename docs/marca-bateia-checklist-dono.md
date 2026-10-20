# Bateia: checklist do dono

Quatro coisas só você pode fazer: renomear o repositório, comprar os domínios, criar o handle e buscar a marca no INPI. Mais um ajuste no painel do Clerk.

Nada aqui foi feito por agente. Nenhuma compra, conta, renomeação ou formulário.

**Regra de ouro (DESIGN.md, topo).** O pacote Python, as imagens e os nomes técnicos continuam `opportunity-radar`. "Bateia" é o nome do produto na interface. Não renomeie `pyproject.toml` `name`, `src/opportunity_radar`, `compose.yaml` `name:`, unidades systemd, `/etc/opportunity-radar`, nem as imagens `ghcr.io/<dono>/opportunity-radar-*`.

Referências de linha são desta branch (`feat/marca-bateia-final`, 2026-10-20). Preços são "valor de referência, confira na hora".

Ordem sugerida: 1 (INPI) primeiro, depois 3 e 2; o 4 (renomear o repositório) fica por último. Se a busca no INPI der no-go, nada do resto vale o dinheiro.

---

## 1. Busca de marca no INPI

**Onde:** busca de marcas do INPI, no portal gov.br/inpi (serviço "Pesquisa de marcas").

**O que fazer**

- [ ] Buscar `Bateia` na classe NCL 9 (software, aplicativos).
- [ ] Buscar `Bateia` na classe NCL 35 (serviços de recrutamento, colocação de pessoal, RH).
- [ ] Buscar `Bateia` na classe NCL 42 (SaaS, plataforma como serviço, desenvolvimento de software).
- [ ] Repetir com busca exata e com busca fonética: `Bateia`, `Batéia`, `Bateya`, `Bateja`, `Batea`, `Batêia`.
- [ ] Anotar todo resultado ativo (pedido em andamento ou registro vigente) nas três classes: titular, classe, situação, número do processo.
- [ ] Olhar também marcas parecidas em classes vizinhas (36, 41, 45) e marcas de alto renome.
- [ ] Guardar capturas de tela com data.

**Como decidir (go/no-go)**

- Go: nada idêntico ou muito parecido ativo em 9, 35 ou 42.
- Atenção: marca parecida em classe diferente, ou pedido arquivado ou extinto. Peça opinião antes de seguir.
- No-go provisório: marca idêntica ou foneticamente igual, ativa, em 9, 35 ou 42, com atividade próxima à de vagas, software ou RH.
- Isto não é parecer jurídico. Consulte um agente de propriedade industrial se houver dúvida.

**Custo de referência.** Depois da busca, o pedido de registro custa R$ 880 por classe, ou R$ 440 com desconto de 50% para pessoa física, MEI, ME e EPP (especificação pré-aprovada). Tabela do INPI, Portaria INPI nº 10/2025, conferida em 2026-10-20 em gov.br/inpi (custos e pagamento). Três classes: R$ 1.320 a R$ 2.640. Confira na hora.

**Riscos**

- A busca não garante registro. O INPI examina o pedido e terceiros podem se opor.
- Em geral, só peça o registro depois de decidir usar o nome: pedido protocolado pode ser indeferido. Confirme com um agente de propriedade industrial se a taxa é devolvida nesse caso.
- Em geral, usar a marca antes do registro não dá prioridade sobre quem pedir antes. Confirme com um agente de propriedade industrial.

**O que muda no código depois:** nada. Se der no-go, o plano de marca volta para as finalistas (Quilate, Pinça) e os itens 2 e 3 não valem.

---

## 2. Criar o handle `bateia-app`

Verificado em 2026-10-20: `bateia-app` estava livre no GitHub. Confira de novo antes de criar.

**Onde:** github.com, "New organization" (recomendado, serve para ser dono do repositório depois) ou novo usuário.

**O que fazer**

- [ ] Confirmar que `github.com/bateia-app` ainda dá 404.
- [ ] Criar a organização `bateia-app` (plano gratuito).
- [ ] Ativar 2FA na conta que for dona.
- [ ] Decidir: manter o repositório em `mathfrancisco` ou transferir para `bateia-app`. A transferência é outra operação (Settings, Danger Zone, Transfer) e muda o dono das imagens GHCR, do Pages e dos secrets. Não faça junto com a renomeação.

**Custo:** gratuito.

**Reservar em outras plataformas (sugestão, só se valer o esforço)**

- [ ] LinkedIn (página da empresa).
- [ ] Instagram e X, mesmo handle `bateia.app` ou `bateiaapp`.
- [ ] npm e PyPI, só se um dia publicar pacote.

**Riscos:** handle livre hoje pode ser tomado amanhã. Se o INPI der no-go, uma organização vazia é inofensiva e pode ser apagada.

**O que muda no código depois:** nada, a não ser que transfira o repositório para a organização. Nesse caso os `git remote` e o texto de `CLAUDE.md:3` mudam como no item 4, e as imagens `ghcr.io/${{ github.repository_owner }}/...` (`.github/workflows/pipeline.yml:779`, `:795`, `:807`, `:814`, `:819`) passam a sair com o novo dono. A VM precisa puxar de lá.

---

## 3. Comprar `getbateia.com` e `bateiaapp.com.br`

Verificado em 2026-10-20: os dois estavam livres. Confira de novo antes de comprar.

**Onde**

- `bateiaapp.com.br`: registro.br. Exige CPF ou CNPJ. É você quem faz.
- `getbateia.com`: um registrador internacional. Cloudflare Registrar é a opção natural, porque o DNS e o Worker já estão na Cloudflare.

**O que fazer**

- [ ] Conferir disponibilidade dos dois no dia.
- [ ] Registrar `bateiaapp.com.br` em registro.br, com o titular certo (CPF ou CNPJ de quem será dono da marca).
- [ ] Comprar `getbateia.com`.
- [ ] Escolher o domínio principal. Sugestão: `getbateia.com`. O outro redireciona para ele.
- [ ] Apontar o DNS para a Cloudflare (zona do domínio). Para o `.com.br`, trocar os servidores DNS no registro.br pelos da Cloudflare.
- [ ] Criar o registro do site: domínio personalizado no Worker (Workers & Pages, aba Domains & Routes).
- [ ] Criar o registro da API: um subdomínio, por exemplo `api.getbateia.com`, apontando para a VM OCI (hoje `<host-da-api>`, ver o runbook de hospedagem). O proxy reverso da VM precisa emitir o certificado para o novo nome.
- [ ] Configurar o redirecionamento 301 do domínio secundário para o principal.
- [ ] Ativar SPF, DKIM e DMARC só se for enviar e-mail do domínio. Não é necessário agora.

**Custo (valor de referência, confira na hora)**

- `.com.br`: R$ 40,00 por ano. Fonte: registro.br, conferido em 2026-10-20.
- `.com`: não conferi. Veja o preço no registrador na hora da compra.

**Riscos**

- Sem CPF ou CNPJ válido, o registro.br não registra.
- O titular do domínio é quem manda nele. Use a conta de quem será dono da marca.
- Domínio comprado antes do INPI pode ficar sem uso. Custo baixo.
- O site hoje roda em `https://opportunity-radar.<seu-subdominio>.workers.dev` (`docs/53-roadmap-hospedagem/evidencias/2026-10-16-f53-fechamento-piloto.md:3`). O domínio novo é adicionado ao lado. Não apague o `workers.dev` até testar.
- Trocar de origem derruba sessões do Clerk. Testar login depois da troca.

**O que muda no código e na configuração depois**

Variáveis de ambiente (não são arquivos versionados, ficam na VM e na Cloudflare; modelo em `docs/53-roadmap-hospedagem/variaveis-e-runbooks.md:21` e `:24`):

- [ ] `FRONTEND_ORIGIN` na VM, em `/etc/opportunity-radar/api.env`: a origem HTTPS exata do site novo, por exemplo `https://getbateia.com`. É a única origem aceita no CORS (`src/opportunity_radar/presentation/http/app.py:83-90`; validação exata em `:36-49`; padrão local em `src/opportunity_radar/platform/config.py:19`; exigida por `compose.cloud.yaml:9`). Sem `www`, sem barra final. A API aceita uma origem só: ao trocar, a antiga para de funcionar.
- [ ] `CLERK_AUTHORIZED_PARTIES` na VM: a mesma origem (`config.py:24`, `compose.cloud.yaml:12`).
- [ ] `VITE_API_BASE_URL` nas variáveis do Cloudflare Workers Builds: a URL pública da API nova, se mudar o host (`apps/web/.env.example:3`). Fazer novo build do site.
- [ ] Reiniciar a API na VM depois de editar o `api.env`.

Arquivos:

- [ ] `apps/web/wrangler.jsonc`: hoje não tem rota nem domínio (`:4` só traz `name`; `:5-:10` o resto). O domínio personalizado pode ser criado pelo painel. Se preferir em código, adicione `routes` com `custom_domain: true`. Mudar `name` (`:4`) muda a URL `workers.dev` e cria um Worker novo: não mude.
- [ ] `apps/web/public/site.webmanifest`: não tem `start_url` nem `scope`. Nada a mudar.
- [ ] `compose.cloud.yaml`: sem origem fixa, só variáveis. Nada a mudar.
- [ ] `.env.example:10`: `FRONTEND_ORIGIN=http://localhost:3000` é local. Não mude.
- [ ] Documentação operacional que cita o `workers.dev` e o host da API, para atualizar quando o domínio entrar no ar: `docs/53-roadmap-hospedagem/README.md:85`, `docs/53-roadmap-hospedagem/evidencias/2026-10-16-f53-piloto-online.md`, `infra/systemd/README.md:73`. Evidências datadas são histórico: deixe como estão.

Painel do Clerk (não é código):

- [ ] Domains / Paths: adicionar o domínio novo e as URLs de redirecionamento de entrada e saída.
- [ ] Origens permitidas (allowed origins) e URLs de redirecionamento: incluir `https://getbateia.com` (e `https://bateiaapp.com.br` se for servir direto).
- [ ] O Clerk está em instância de desenvolvimento (`docs/53-roadmap-hospedagem/evidencias/2026-10-16-f53-fechamento-piloto.md:5`). Domínio próprio em produção costuma pedir instância de produção, com chaves novas (`VITE_CLERK_PUBLISHABLE_KEY`, `CLERK_ISSUER`, `CLERK_JWKS_URL`) e DNS do Clerk. É uma decisão à parte: confira a documentação do Clerk antes.

---

## 4. Renomear o repositório GitHub

Hoje: `mathfrancisco/Opportunity-Radar`. Sugestão: `bateia` (se o handle do item 2 existir e o repositório for transferido, `bateia-app/bateia`). Faça por último: é a ação com mais efeito colateral.

**Onde:** GitHub, repositório, Settings, General, "Repository name", Rename.

**O que fazer**

- [ ] Confirme quem tem clone local do repositório (além de você e dos worktrees) e avise.
- [ ] Antes: anotar PRs abertos e secrets/variables do Actions (eles permanecem, mas confira).
- [ ] Renomear no GitHub.
- [ ] Atualizar o `origin` em todo clone e worktree (comandos abaixo).
- [ ] Rodar o pipeline uma vez na `main` para ver que o CI passa.

**Custo:** gratuito.

**Como o GitHub trata o nome antigo (não verificado, escrito de memória: confira em "Renaming a repository" na documentação do GitHub antes de renomear)**

- A página do repositório, issues, PRs, `git clone`, `fetch` e `push` no nome antigo continuam funcionando por redirecionamento.
- O redirecionamento morre se alguém criar um repositório novo com o nome antigo na mesma conta. Não crie.
- GitHub Pages não redireciona. Este repositório não usa Pages (o site vai por Cloudflare Workers), então não há efeito. Confirme em Settings, Pages.
- Workflows de outros repositórios que usam `uses: mathfrancisco/Opportunity-Radar/...` quebram no nome antigo.
- [ ] Confirme que nenhum outro repositório usa este como action.
- Badges: nenhum no README hoje. Se existir em outro lugar, atualize a URL.
- Imagens GHCR: o nome vem de `${{ github.repository_owner }}/opportunity-radar-<imagem>` (`.github/workflows/pipeline.yml:779`), não do nome do repositório. A renomeação não muda. Depois de renomear, confira em Packages se cada pacote continua ligado ao repositório.
- Integrações ligadas ao repositório (Cloudflare Workers Builds, Dependabot, apps instalados) seguem o ID, mas confira no painel do Cloudflare que a conexão com o Git continua verde.

**Comandos para os clones e worktrees**

Worktrees compartilham o `.git` do clone principal, então um `set-url` no clone principal vale para todos. Os clones separados precisam do seu:

```
git remote set-url origin https://github.com/mathfrancisco/bateia.git
git remote -v
```

Todos os diretórios de `git worktree list` (inclusive o do Codex) compartilham o mesmo `.git`. Se existir algum clone feito à parte com `git clone`, rode o `set-url` nele também. A pasta local `Opportunity-Radar` pode ficar com o nome antigo.

**O que muda no código depois**

Mudar:

- [ ] `CLAUDE.md:3`: "This is the public `mathfrancisco/Opportunity-Radar` repository" para o nome novo.
- [ ] Sua configuração local de agentes (memória e instruções globais) que cita o repositório, fora do repositório.
- [ ] `README.md:1`, `:5`, `:170` dizem "Opportunity Radar" como nome do produto. Trocar por "Bateia" é decisão de texto, separada da renomeação do repositório. Não é obrigatório para o rename funcionar.
- [ ] Links de docs que apontam para `github.com/mathfrancisco/Opportunity-Radar`: a busca no repositório fora de `docs/` não achou nenhum. Dentro de `docs/` os links antigos continuam por redirecionamento. Atualize só os que importam.

Não mudar (nome técnico, ver regra de ouro):

- `pyproject.toml:6` (`name = "opportunity-radar"`) e `:32` (script `opportunity-radar-worker`).
- `apps/web/package.json:2` (`@opportunity-radar/web`) e `tests/e2e/browser/package.json:2`.
- `apps/web/wrangler.jsonc:4`: `name` do Worker, define a URL `workers.dev`.
- `compose.yaml:1`, `:173`; `compose.cloud.yaml:1`.
- `.github/workflows/pipeline.yml:779`, `:795`, `:807`, `:814`, `:819` (nomes de imagem).
- `infra/systemd/*`, `infra/terraform/oci/*`, `scripts/*`, `src/opportunity_radar/*`, `tests/*`.
- `apps/web/src/copy.test.ts:8`: lista "Opportunity Radar" como texto proibido na interface. Fica.

Não existe `.github/workflows` com URL do repositório fixa: o pipeline usa `github.repository` e `github.repository_owner`. Não há `repository`/`homepage`/`urls` em `pyproject.toml`. Não há badges no README.

---

## 5. Clerk: nome do aplicativo

Na captura final, a tela de cadastro ainda mostra "Opportunity Radar". O nome vem do painel do Clerk, não do código.

- [ ] Clerk Dashboard, aplicativo, Settings (ou "Application name"): trocar para `Bateia`.
- [ ] Se houver logotipo de aplicativo no Clerk, subir o ícone da Bateia (`apps/web/public/icon-512.png`).
- [ ] Se houver instância de produção além da de desenvolvimento, repetir nas duas.
- [ ] Abrir a tela de cadastro e confirmar que o título mudou.

Custo: nenhum. Código: nenhuma mudança.

---

## Quadro final

| # | Item | Custo de referência | Muda código? |
| --- | --- | --- | --- |
| 1 | Busca INPI (classes 9, 35, 42) | busca gratuita; pedido R$ 440 a R$ 880 por classe | não |
| 2 | Handle `bateia-app` | gratuito | só se transferir o repositório |
| 3 | Domínios | `.com.br` R$ 40/ano; `.com` não conferido | nenhum arquivo obrigatório; variáveis na VM, Cloudflare e Clerk |
| 4 | Renomear repositório | gratuito | `CLAUDE.md:3` e remotes locais |
| 5 | Nome no Clerk | gratuito | não |

Fontes conferidas em 2026-10-20: registro.br (página "Sobre domínios"), tabela de retribuições do INPI (Portaria INPI nº 10/2025, gov.br/inpi). O comportamento de redirecionamento do GitHub é da documentação "Renaming a repository": releia antes de renomear.
