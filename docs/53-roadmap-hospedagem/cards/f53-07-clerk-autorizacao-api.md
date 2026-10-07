# F53-07 — Clerk e autorização da API

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-02.

## Objetivo e estado atual

O Opportunity Radar atual é pessoal e não tem autenticação de múltiplos
usuários. Este card introduz um único dono autorizado, sem transformar produto
em multiusuário. A API, não o frontend, valida o JWT e impõe o vínculo imutável
`user_id = sub`.

## Implementação futura

1. Escolher instância Clerk de produção com domínio próprio e registrar
`<CLERK_ISSUER>`, JWKS, algoritmo permitido e `<OWNER_SUB>` no cofre/configuração
segura. Não usar segredo ou chave `sk_` no frontend.
2. Implementar dependência de autenticação no backend e testes futuros, por
   exemplo em `tests/backend/presentation/test_auth.py`; o arquivo ainda não
   existe. Usar SDK Python/documentação Python, não copiar API JavaScript.
3. Buscar JWKS por URL do issuer com cache limitado e validar assinatura,
   issuer, algoritmo, `exp` e `nbf`. Rejeitar algoritmo inesperado, chave não
   encontrada, token expirado e issuer diferente.
4. Validar `azp` contra origins autorizadas. Validar `aud` somente quando o
   template/token estiver configurado para emitir audiência, documentando esse
   contrato em vez de exigir claim ausente.
5. Mapear somente `sub` ao dono imutável `<OWNER_SUB>`; recusar outro usuário,
   organização ou claim de papel como atalho de privilégio.
6. Aplicar autenticação a toda rota privada, deixando apenas `/health/live`
   pública para liveness. Nunca registrar bearer token, header Authorization,
   payload JWT ou JWKS inteiro.

## Resultado e falhas

Espera-se `401` para token ausente, expirado, assinatura/issuer/algoritmo
inválidos e `403` para `sub` válido que não é o dono. Falha de JWKS deve falhar
fechada nas rotas privadas; não aceitar token sem verificação para manter o
serviço disponível.

## Aceite

| ID | Teste futuro | Resultado |
| --- | --- | --- |
| AC01 | JWT Clerk válido do `<OWNER_SUB>` | rota privada responde conforme contrato |
| AC02 | token sem assinatura, exp, nbf ou issuer corretos | `401`, sem vazamento |
| AC03 | token válido de outro `sub` | `403` |
| AC04 | `azp` inválido e `aud` configurado inválido | recusados; `aud` ausente só é aceito se não configurado |
| AC05 | log de falha de auth | contém motivo/correlation ID, nunca token |

Preservar relatório de testes e configuração redigida. A ausência dos testes
futuros significa que este card permanece planejado.

## Configuração, testes e operação

Armazene issuer, allowlist de `<OWNER_SUB>` e segredo Clerk no cofre por
ambiente. A chave publishable é a única chave admitida no browser. A dependência
Python e a API exata devem ser escolhidas pelo lockfile e documentação do SDK,
não por snippet JavaScript.

1. Configure JWKS, algoritmos permitidos, issuer e `authorized_parties`.
2. Configure `aud` apenas se template realmente o emitir.
3. Proteja leitura e escrita; mantenha somente `/health/live` público e mínimo.
4. Exercite matriz 401/403/200 com fixtures offline, inclusive rotação de `kid`.
5. Revise logs: correlação e motivo podem existir; bearer/JWT/e-mail não.

Em indisponibilidade JWKS, rotas privadas falham fechadas. Não introduza bypass
de produção para CI; F53-15 deve usar JWT/JWKS fixture em ambiente isolado.

## Contrato de fixture e matriz de rotas

F53-07 cria fixtures offline assinadas por chave de teste e JWKS local para CI.
Não use sessão, chave, browser ou instância Clerk real como fixture.

| Caso | Payload e header JOSE | Resultado esperado |
| --- | --- | --- |
| dono válido | payload `iss`, `sub=<OWNER_SUB>`, `exp`, `nbf`; header `alg`, `kid` | rota privada autorizada |
| token vencido | `exp` no passado | `401` |
| issuer/algoritmo errado | payload `iss` ou header `alg` diferente | `401` |
| outro usuário | `sub` diferente | `403` |
| origem não autorizada | `azp` divergente | `401` ou `403` pelo contrato |

1. Declare `aud` somente se o template emitir audiência; teste divergência e
   ausência segundo esse contrato.
2. Exercite rotação de `kid`: chave removida falha fechada, chave nova funciona
   após atualizar JWKS.
3. Aplique autenticação às rotas de leitura e escrita; confirme `/health/live`
   público, mínimo e sem detalhes internos.
4. Registre método, rota, código e correlation ID redigidos, nunca JWT ou e-mail.

Se a biblioteca não validar todos os claims necessários, pare e escolha uma
integração compatível com lockfile e documentação Python. Nunca decodifique o
payload como substituto da assinatura.

## Rollback e gate

Desativar rota pública recém-exposta ou restaurar a versão sem login somente
antes de dados reais; nunca tornar endpoints privados anônimos como correção.
F53-08, F53-09 e F53-15 exigem todos os ACs.
