# F53-08 — Clerk no frontend e Cloudflare Pages

**Prioridade:** P1. **Estado:** planejado. **Depende de:** F53-02, F53-07.

## Objetivo

Publicar o frontend estático em Pages e fazê-lo obter token Clerk somente para
chamar API HTTPS. Nenhuma chave secreta é aceitável em build ou variável `VITE_`.
O app atual não possui esta configuração de Pages ou Clerk.

## Procedimento futuro

1. Criar projeto Pages do repositório certo com build root `apps/web`, comando
   `npm ci && npm run build` e diretório de saída `dist`; confirmar estes campos
   no console antes do primeiro deploy.
2. Configurar somente `VITE_API_BASE_URL=https://api.<DOMINIO>` e
   `VITE_CLERK_PUBLISHABLE_KEY=<pk_publica>` como valores públicos de build.
   Não prefixar segredos, URL Neon ou credenciais OAuth com `VITE_`.
3. Registrar domínio próprio `app.<DOMINIO>` após F53-02. Usar `pages.dev` só
   no piloto de desenvolvimento; confirmar que SPA sem `404.html` recebe o
   comportamento de fallback documentado pelo Pages.
4. Integrar provider Clerk e cliente da API para enviar bearer token a destino
   permitido, sem guardar token em log, URL, localStorage manual ou relatório.
5. Testar login/logout e navegação direta em rota SPA com usuário dono e com
   usuário não autorizado. Verificar que chamada sem token recebe resposta da
   API, não um falso sucesso de UI.
6. Arquivar build ID, commit, domínio mascarado e resultados de navegador em
   evidência redigida.

## Aceite

| ID | Positivo | Negativo/operacional |
| --- | --- | --- |
| AC01 | Pages constrói em `apps/web` e publica `dist` | root errado falha antes de promover |
| AC02 | apenas URL API e chave pública estão em `VITE_` | segredo em variável build bloqueia deploy |
| AC03 | dono navega e chama API autenticada | outro usuário recebe `403` da API |
| AC04 | rota SPA direta não gera 404 indevido | testar sem `404.html` no domínio piloto |

## Configuração Pages e teste de browser

No console Pages, conecte somente branch/commit aprovado e informe **Root
directory** `apps/web`, **Build command** `npm ci && npm run build` e **Build
output directory** `dist`. Defina preview e produção separadamente; não presuma
que o fluxo Git oferece um campo separado de instalação.

1. Adicione `VITE_API_BASE_URL=https://api.<DOMINIO>` e a publishable key Clerk.
2. Gere preview antes de domínio próprio e abra janela privada.
3. Teste `/`, rota interna, reload da rota interna e URL de asset real.
4. Confirme que `dist/404.html` não existe quando depender do fallback SPA
   padrão do Pages; não adicione catch-all que capture asset.
5. Teste login/logout, dono permitido, outro `sub`, token ausente e API HTTPS.
6. Guarde build ID, commit e resultados redigidos; não guarde token de sessão.

Diagnóstico: build falho geralmente aponta root/output errado; rota profunda
falha quando um `404.html` ou redirect contradiz o fallback; 401/403 é contrato
da API e não deve ser mascarado pela UI. Reverter é escolher deployment Pages
anterior depois de confirmar que suas variáveis e origem ainda são compatíveis.

## Ambientes, build e evidência de navegador

Use a configuração abaixo só no console Pages, após confirmar que
`apps/web/package.json` fornece os comandos. Ela documenta o contrato desejado,
não configura Pages a partir deste card.

```text
Production branch: <branch-aprovada>
Root directory: apps/web
Build command: npm ci && npm run build
Build output directory: dist
```

| Ambiente | Valor público permitido | Verificação |
| --- | --- | --- |
| Preview | `VITE_API_BASE_URL` piloto e `VITE_CLERK_PUBLISHABLE_KEY` | preview e commit |
| Produção | `https://api.<DOMINIO>` e chave pública | domínio e release |

1. Rode `npm ci` e `npm run build` somente no Pages ou estação com dependências
   aprovadas; capture status e commit, nunca `.env`.
2. Abra preview anônimo em janela privada e teste `/`, rota interna, reload e
   URL de asset. SPA carrega rota interna; asset inexistente continua 404.
3. Use DevTools só para hostname, HTTPS e status API. Remova token de capturas.
4. Teste `401` sem sessão, fluxo do dono e `403` de outro usuário. A UI pode
   orientar login, mas não pode declarar sucesso para resposta bloqueada.
5. Promova somente build cujo commit, configuração e origem constem na prova.

Chave com prefixo `VITE_` é pública. Se segredo entrar no bundle ou variável de
build, pause, remova deployment e rotacione esse segredo.

## Rollback e gate

Reverter para o deployment Pages anterior e o record DNS documentado em F53-02.
Invalidar configuração pública incorreta e rotacionar segredo se ele tiver sido
exposto. F53-16 requer a prova de piloto deste card; ele não autoriza cutover.
