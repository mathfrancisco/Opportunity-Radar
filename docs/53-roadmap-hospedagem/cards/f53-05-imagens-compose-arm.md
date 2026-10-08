# F53-05 — imagens e Compose ARM

**Prioridade:** P0. **Estado:** planejado. **Depende de:** F53-04.

## Objetivo

Provar que API e jobs executam imagens ARM verificadas e que o frontend é
estático no Pages. A VM não hospeda PostgreSQL, Redis, build do frontend ou
runtime do frontend. Hoje `compose.cloud.yaml` e `scripts/run_pipeline_once.py`
não existem; estes são arquivos futuros, não comandos disponíveis agora.

## Sequência futura

1. Inspecionar Dockerfiles e dependências para identificar imagem base ARM64 e
   build multiarch. Não assumir que um `--target runtime-worker` existe.
2. Criar futuro `compose.cloud.yaml` que separe proxy, API e job finito; usar
   variáveis injetadas pelo cofre/ambiente, sem valores no arquivo.
3. Construir e executar a imagem na arquitetura A1 em ambiente de piloto.
   Verificar endpoint de saúde, migração explicitamente controlada e encerramento
   gracioso do processo.
4. Manter API e job com comandos distintos. O job sai após a janela e não fica
   como worker ou scheduler residente.
5. Confirmar que a imagem publicada não contém `.env`, dump, chave, state ou
   segredo em camadas. Não provar isso com `docker inspect` que imprima env.
6. Registrar digest, plataforma, revisão, duração e saída redigida do health
   check. Falha de arquitetura exige corrigir build, não emular x86 em produção.

## Resultado e correção

O resultado é um artefato ARM executável e Compose sem banco local. `exec format
error` indica imagem/plataforma incompatível; reinício contínuo indica comando,
health check ou variável ausente. Parar, corrigir em piloto e preservar o
artefato de falha redigido antes de nova imagem.

## Aceite

| ID | Critério | Prova |
| --- | --- | --- |
| AC01 | imagem executa em ARM64 | digest, plataforma e health check |
| AC02 | Compose não sobe PostgreSQL, Redis ou frontend runtime | configuração redigida revisada |
| AC03 | job finito encerra no deadline | log redigido de início, claim e saída |
| AC04 | imagem não carrega segredos versionados | revisão de contexto e camadas |

Teste negativo: executar imagem x86 na A1 deve ser rejeitado antes do deploy.
Teste operacional: reiniciar API sem executar job e executar job sem expor API.

## Pipeline de imagem e configuração cloud

F53-05 cria o primeiro `compose.cloud.yaml`; este card não pode reaproveitar o
Compose local como se fosse produção. Ele contém apenas `migrate`, `api`,
`worker` e proxy, sem PostgreSQL, frontend Node ou volume de banco local.

1. Faça CI construir API e worker para ARM64 e publicar somente digest imutável.
2. Registre commit, digest, plataforma e resultado de inicialização.
3. Faça o host puxar o digest aprovado, não tag mutável.
4. Passe secrets por cofre/arquivo protegido; valide apenas nomes, nunca valor.
5. Faça o healthcheck frequente chamar `/health/live`, não `/health` ou
   `/health/ready`, pois os dois últimos consultam Neon.
6. Execute migration uma vez antes de API/worker e pare no primeiro erro.

Teste negativo: manifest sem ARM64, digest divergente, variável secreta em
`VITE_*` ou healthcheck DB frequente bloqueiam o release. Rollback usa digest
anterior registrado e não remove dados ou state.

## Contrato Compose e verificação de artefato

O trecho é contrato futuro de `compose.cloud.yaml`, não arquivo existente nem
comando pronto para produção. Ele torna visível o que o revisor deve procurar:

```yaml
services:
  api:
    image: <REGISTRO>/opportunity-radar-api@sha256:<DIGEST_ARM64>
    healthcheck:
      test: ["CMD", "<CLIENTE_HTTP>", "-f", "http://localhost:<PORT>/health/live"]
  worker:
    image: <REGISTRO>/opportunity-radar-worker@sha256:<DIGEST_ARM64>
    restart: "no"
```

1. Faça a CI registrar plataforma publicada, digest, commit e resultado de
   inspeção do manifest sem imprimir variáveis de ambiente.
2. Antes de subir API, confira que o digest solicitado é o digest aprovado, que
   declara `linux/arm64`, e que API/worker usam comandos diferentes.
3. Confirme que o healthcheck chama `/health/live`; `/health` e `/health/ready`
   tocam Neon no código atual e um probe a cada 10 segundos impede escala zero.
4. Verifique configuração final: só proxy, API, migration finita e worker finito;
   rejeite `postgres`, `redis`, frontend Node, scheduler residente e volume DB.
5. Registre duração do job e saída final. Timeout, falha ou reinício contínuo
   precisa parar a promoção, conservar log redigido e manter digest anterior.

O healthcheck apenas prova liveness de processo. Readiness com banco ocorre no
deploy ou sob demanda controlada; ela não deve virar monitor frequente.

## Rollback e gate

Reimplantar o digest anterior conhecido e parar novos jobs; não restaurar banco
para resolver falha de imagem. F53-09, F53-10, F53-12 e F53-15 dependem de
todos os ACs.
