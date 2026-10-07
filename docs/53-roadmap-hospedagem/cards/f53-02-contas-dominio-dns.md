# F53-02 — contas, domínio e DNS

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-01. Consulte o
[runbook](../../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md).

## Objetivo e estado atual

Controlar propriedade, recuperação e nomes antes de apontar tráfego. Hoje não
há domínio, zona DNS, organização de produção Cloudflare ou Clerk confirmados
no repositório. O resultado futuro reserva `app.<DOMINIO>` e `api.<DOMINIO>`
para o mesmo dono operacional, sem expor segredos.

## Procedimento futuro

1. Confirmar com o registrador o proprietário, renovação, MFA, contato de
   recuperação e autorização para alterar nameservers.
2. Criar ou selecionar a organização Cloudflare pertencente ao dono e importar
   a zona somente após registrar o estado DNS atual redigido.
3. Criar os subdomínios `app.<DOMINIO>` e `api.<DOMINIO>` no inventário. Não
   apontar A, AAAA ou CNAME antes de F53-04, F53-08 e F53-09.
4. Registrar TTL inicial, responsável por cada record e janela de alteração;
   manter o record anterior para reversão enquanto o novo caminho é piloto.
5. No Clerk, selecionar instância de produção e domínio próprio depois de
   confirmar que a organização, OAuth e e-mail pertencem ao dono. `pages.dev`
   fica restrito a desenvolvimento.
6. Salvar somente uma matriz redigida: nome, tipo de record, destino mascarado,
   TTL, dono, data e motivo. Não salvar zone export, IDs, tokens ou e-mails.
7. Parar se registrar, DNS e Clerk tiverem proprietários diferentes sem acordo
   de recuperação escrito.

## Resultado e tratamento de erro

Espera-se que DNS ainda não direcione produção; a saída é autorização e um
plano reversível. Propagação incompleta, domínio sem MFA ou OAuth de pessoa
individual são falhas: restaurar o record anterior, remover a alteração de
piloto e corrigir propriedade antes de repetir.

## Aceite e evidência

| ID | Critério | Evidência |
| --- | --- | --- |
| AC01 | dono e recuperação de domínio, DNS e Clerk estão registrados | matriz redigida e aprovada |
| AC02 | `app` e `api` têm reserva sem exposição prematura | captura DNS redigida com TTL |
| AC03 | produção Clerk usa domínio próprio e OAuth do dono | tela redigida de configuração |
| AC04 | record anterior e janela de rollback existem | procedimento datado de restauração |

Teste negativo: tentar avançar com `pages.dev` como produção ou com credencial
OAuth pessoal deve bloquear F53-08. Prova operacional: revisar uma alteração
DNS em ambiente piloto e confirmar que o antigo destino pode voltar dentro do
TTL planejado.

## Checklist de alteração DNS

1. Confirme ambiente e zona pelo domínio, sem busca de organização parecida.
2. Registre valores atuais redigidos, TTL e hora antes da alteração.
3. Declare um record, destino esperado, dependência e forma de retorno.
4. Aplique em janela aprovada e consulte resolução de rede externa.
5. Compare hostname, tipo de record e certificado; cache local não basta.
6. Se resolver ao destino errado, restaure o record documentado e aguarde TTL.

Nunca use export bruto de zona, token DNS, e-mail ou ID de conta como evidência.
A prova negativa é consulta externa mostrando que `api` ainda não aponta ao
proxy antes de F53-09.

## Parâmetros Clerk e domínio de produção

Antes de habilitar domínio Clerk, use esta matriz para separar valores públicos
de credenciais que permanecem no cofre. Ela não autoriza criar OAuth nem trocar
DNS neste card.

| Item | Dono e local | Evidência aceitável |
| --- | --- | --- |
| domínio `app`/`api` | registrador e zona Cloudflare do dono | matriz com nome/TTL mascarados |
| domínio Clerk | instância de produção do dono | tela redigida com estado verificado |
| OAuth redirect URI | provedor OAuth pertencente ao dono | lista de origins sem client secret |
| recuperação/MFA | conta pessoal designada | confirmação de fluxo, sem e-mail/telefone |

1. Confirme que origin e redirect URI usam `https://app.<DOMINIO>` e não
   `pages.dev` como valor de produção.
2. Não valide OAuth por login de outra pessoa ou conta pessoal temporária.
3. Registre record de verificação requerido pelo Clerk como pendente, tipo e
   TTL; espere F53-08/F53-09 antes de apontar tráfego de aplicativo.
4. Consulte resolução de fora da rede após mudança. Resultado esperado é nome,
   tipo e TTL planejados, não apenas cache do computador administrativo.
5. Se domínio não verificar dentro da janela, restaure somente o record alterado
   e investigue conflito de CNAME, nameserver ou TTL antes de repetir.

Uma tela de domínio verificado não substitui a prova de recuperação de conta.
Se o dono não consegue recuperar registrador, Cloudflare e Clerk, bloqueie o
piloto mesmo que o DNS resolva corretamente.

## Rollback e gate

### Handoff operacional

Entregue matriz de propriedade, reserva de nomes, TTL e record anterior
mascarado. O próximo executor precisa saber quem aprova DNS e quem pode reverter
sem receber token, export de zona ou credencial OAuth.

Repita a conferência ao trocar registrador, administrador Cloudflare, e-mail de
recuperação ou provedor OAuth. Essas trocas invalidam a prova de propriedade.

Restaurar somente o record documentado e invalidar configuração de piloto se a
validação falhar. Não alterar nameserver como forma de rollback. F53-04,
F53-07 e F53-08 exigem AC01–AC04.
