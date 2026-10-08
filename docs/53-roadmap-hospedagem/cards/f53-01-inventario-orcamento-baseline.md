# F53-01 — inventário, orçamento e baseline

**Prioridade:** P0. **Estado:** planejado, não implementado. **Depende de:** —.
Leia o [runbook de hospedagem](../../53-plano-hospedagem-cloudflare-oracle-neon-clerk.md)
antes de agir.

## Objetivo e razão concreta

Produzir uma fotografia redigida do serviço atual, das contas que terão dono e
dos limites econômicos. Sem esta linha de base, uma conta gratuita excedida, uma
instância recuperada por ociosidade ou uma métrica posterior não pode ser
atribuída a uma mudança.

**Verificado hoje:** o aplicativo é pessoal e não tem autenticação Clerk,
Terraform OCI, Pages, VM ou Neon configurado neste repositório. **Planejado:**
definir responsáveis e medição antes de provisionar.

## Arquivos e limites futuros

Após a implementação, a evidência poderá viver em
`docs/53-roadmap-hospedagem/evidencias/f53-01-baseline-<data>.md`. Não criar
esse arquivo para simular execução. Nenhuma alteração de código é parte deste
card.

## Sequência

1. Registrar, fora do repositório, uma pessoa recuperadora para OCI,
   Cloudflare, Neon, Clerk e o registrador do domínio.
2. Registrar mês, moeda, teto efetivamente aprovado e responsável por qualquer
   custo. A meta é zero fora das franquias até haver aprovação externa. Os
   US$100 de crédito AWS, quando existirem, pertencem só ao fallback AWS e não
   pagam OCI, Neon, Clerk ou Cloudflare.
3. Abrir os painéis dos provedores e anotar plano, região, quota exibida,
   consumo inicial e URL da página, omitindo identificadores e e-mails.
4. Fixar como meta mensal Neon `<=80 CU-h` e `<1 GB`; tratar 100 CU-h como
   limite anunciado a confirmar no painel, não como margem para consumo.
5. Registrar OCI A1 como alvo de 2 OCPUs/12 GB, 1.500 OCPU-h, 9.000 GB-h e
   boot inicial de 50 GB. Confirmar no console capacidade ARM e franquia da
   tenancy; nunca criar carga artificial para evitar recuperação por ociosidade.
6. Medir hoje contagem de dados, duração de uma coleta e memória/CPU locais
   como referência, removendo URLs, nomes privados e payloads da evidência.
7. Parar se uma conta, domínio, região ou teto não tiver proprietário humano.

## Resultado, falhas e correção

O resultado esperado é uma tabela datada com zero recursos ou recursos já
existentes explicitamente identificados, limite, medição e dono. Capacidade A1
indisponível, quota diferente ou plano pago ativo exige pausar e replanejar;
não contornar escolhendo região, shape ou cartão sem aprovação registrada.

## Aceite e provas

| ID | Prova positiva | Prova negativa ou operacional |
| --- | --- | --- |
| AC01 | cada provedor tem dono e recuperação fora do Git | remover um dono do rascunho bloqueia F53-02 |
| AC02 | orçamento informa moeda, teto aprovado e Neon <=80 CU-h | projeção >80 CU-h abre decisão, não deploy |
| AC03 | baseline mostra data, unidade e fonte | captura com segredo, e-mail ou URL privada é rejeitada |
| AC04 | capacidade OCI foi conferida no console | "Always Free" lido em página pública não basta |

Guardar captura redigida, export de métricas e decisão de custo sob caminho de
evidência futuro. Redigir chaves, tokens, IDs de tenancy, IPs e URLs internas.

## Formato de evidência e diagnóstico

Use uma tabela redigida, uma linha por provedor, com data/hora UTC, ambiente,
plano exibido, unidade, consumo inicial, teto, alerta, dono e fonte oficial.
Substitua valores identificadores por `<mascarado>`.

1. Compare consumo do painel à unidade do limite antes de calcular projeção.
2. Registre se o número é medido, estimado ou limite anunciado.
3. Calcule projeção Neon explicitando horas e CU; não arredonde para caber.
4. Abra alerta de custo/uso quando o provedor permitir e salve prova redigida.
5. Peça revisão do dono antes de marcar a evidência como aceita.

Se painel e página oficial divergirem, o painel da conta vence para a decisão
operacional. Sem alerta disponível, defina verificação manual e responsável.

## Coleta local e cálculo revisável

Faça a coleta no PowerShell local, sem login automatizado nos provedores e sem
copiar valores secretos para terminal compartilhado.

```powershell
git rev-parse HEAD
git status --short
(Get-Date).ToUniversalTime().ToString('o')
```

1. Use a revisão e hora para identificar a medição; omita caminhos locais e
   nomes de usuário do relatório.
2. Para Neon, registre CU configurada, horas e produto. Exemplo: `0,25 CU ×
   24 h × 31 dias = 186 CU-h`; isso excede a meta de 80 CU-h.
3. Para OCI, registre região e capacidade A1 exibida no painel da tenancy.
4. Para domínio, registre custo anual, moeda, vencimento e dono somente se
   aquisição ou renovação for necessária.
5. Faça o responsável comparar total estimado e teto aprovado antes de F53-02.

Sem teto aprovado, o resultado aceito é `não autorizado`; nenhum recurso pode
ser criado como experimento de preço.

## Rollback e gate

### Handoff operacional

Entregue ao próximo card somente: tabela redigida, data da leitura, decisão de
orçamento, limite de alerta e nome do responsável. Não entregue print sem
contexto, planilha com fórmulas ocultas ou acesso a conta como evidência.

Releia o baseline depois de sete dias ou antes de mudar plano, região, quota ou
domínio. Qualquer mudança material reabre F53-01; o consumo anterior não prova
capacidade futura.

Não há recurso a reverter. Se a preparação criou qualquer cobrança ou recurso,
interromper e encaminhar ao dono da conta antes de prosseguir. F53-02 e F53-03
ficam bloqueados até AC01–AC04 terem evidência datada.
