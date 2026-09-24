# CARD F16-01 — GPU, imagem 0.34.4, `ollama-init` e perfis de execução

- **Status:** Em revisão (PR #18)
- **Fase:** 16 — Camada local de IA
- **Depende de:** Nenhum
- **Bloqueia:** F16-02, F16-09, Milestone O
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §3.1, §3.3, §10

## Resultado

O Ollama roda na RTX 5060, na versão 0.34.4 fixada por digest, com os dois modelos
baixados sem terminal, e o compose continua subindo numa máquina sem GPU e no CI.

## Contexto

O serviço `ollama` do `compose.yaml` usa `ollama/ollama:0.5.13` e não reserva GPU nenhuma.
O container não enxerga a placa, então toda análise roda hoje nos 14 núcleos do Xeon
E5-2680 v4, competindo com Postgres, API e worker pelos 16 GB de RAM. Mesmo com a GPU
reservada, a 0.5.13 é anterior ao suporte a Blackwell (CUDA 12.8): o problema de placas
RTX 50 ficando em CPU só foi corrigido em novembro de 2025
([ollama/ollama#13163](https://github.com/ollama/ollama/issues/13163)).

O modelo também não se instala sozinho: o runbook manda rodar `ollama pull` à mão
(`docs/30-runbook.md:211`), e um ambiente novo sobe com a análise degradada até alguém
lembrar disso.

## Escopo

- **Imagem:** `ollama/ollama:0.34.4@sha256:8262851b2846b87c649eddf3e76beb270c52f4d1bc94559f47efde16b0841551`
  no serviço `ollama`, e a mesma referência no `ollama-init`.
- **Reserva de GPU** no serviço `ollama`:

  ```yaml
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  ```

- **Variáveis do servidor** no serviço `ollama`, todas sobrescrevíveis pelo `.env`:
  `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_NUM_PARALLEL=1`,
  `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_KEEP_ALIVE=30m`.
- **Limite de RAM** (`mem_limit`, padrão `6g`, variável `OLLAMA_MEMORY_LIMIT`): se o modelo
  transbordar da VRAM, quem sofre é o Ollama, não o Postgres.
- **Serviço `ollama-init`:** mesma imagem, `OLLAMA_HOST=http://ollama:11434`, roda
  `ollama pull "$OLLAMA_MODEL_ANALYSIS" && ollama pull "$OLLAMA_MODEL_EMBEDDING"` e termina.
  Depende de `ollama` saudável. Nenhum serviço depende dele.
- **`compose.cpu.yaml`:** override que remove a reserva (`deploy: !reset null`) para
  máquinas sem GPU NVIDIA, e target `make up-cpu`.
- **`compose.ci.yaml`:** o mesmo `deploy: !reset null` no serviço `ollama`, que no CI é o
  Ollama falso em Python. O runner não tem GPU.
- **Runbook:** pré-requisitos no Windows (Docker Desktop com backend WSL2, driver NVIDIA
  recente, "Use the WSL 2 based engine" ligado), como conferir que o modelo está na GPU
  (`docker compose exec ollama ollama ps`, coluna `PROCESSOR` = `100% GPU`) e como subir
  sem GPU.
- **`doctor`:** passa a informar a versão do servidor (`GET /api/version`) e, para cada
  modelo carregado (`GET /api/ps`), `size` × `size_vram`. Modelo carregado com
  `size_vram < size` é aviso: parte dele está na RAM.

## Fora de escopo

- Trocar o modelo padrão (F16-02) e mudar o payload da chamada.
- Medir latência (F16-03) — este card só garante que a medição será feita no caminho certo.
- Suporte a GPU AMD ou Apple.

## Notas de implementação

- `!reset` exige Docker Compose 2.24 ou mais recente. O runner `ubuntu-latest` e o Docker
  Desktop atual atendem; o runbook registra a versão mínima.
- O CI só sobe `api worker frontend` e seus `depends_on`. Como nada depende do
  `ollama-init`, ele não roda no CI e não baixa 6 GB de modelos; o passo
  `docker compose config --quiet` continua validando a definição dele.
- O healthcheck atual do `ollama` (`ollama list`) funciona na 0.34.4; o `ollama-init`
  espera por ele com `condition: service_healthy`.
- O digest foi lido do Docker Hub em 24/09/2026 para a tag `0.34.4` (amd64 e arm64). Ao
  implementar, conferir de novo — tag pode ser republicada, digest não.
- No Windows, o driver NVIDIA do host é o que o WSL2 expõe ao container; não se instala
  driver dentro da imagem.

## Critérios de aceite

- [ ] `compose.yaml` referencia a imagem 0.34.4 por digest nos dois serviços.
- [ ] Na máquina de referência, `ollama ps` mostra o modelo de análise com `100% GPU`.
- [ ] `docker compose -f compose.yaml -f compose.cpu.yaml up` sobe numa máquina sem GPU.
- [ ] `ollama-init` baixa os dois modelos configurados e termina com código 0; rodar de
      novo é idempotente.
- [ ] O `doctor` mostra a versão do servidor e avisa quando um modelo carregado não está
      inteiro na VRAM.
- [ ] O job de compose do CI continua verde com o Ollama falso.

## Verificação

- **CI:** `docker compose -f compose.yaml -f compose.ci.yaml config --quiet` valida as
  duas definições; o E2E existente prova que o Ollama falso sobe sem reserva de GPU.
- **Máquina de referência (manual, registrado no PR):** `docker compose up -d`, esperar o
  `ollama-init` terminar, `docker compose exec ollama ollama ps` depois de uma análise, e
  a saída do `doctor`. Colar as três saídas no PR.

## Arquivos prováveis

- `compose.yaml`, `compose.ci.yaml`, `compose.cpu.yaml` (novo)
- `Makefile`
- `scripts/doctor.py`
- `docs/30-runbook.md`, `docs/25-docker-execucao-local.md`
- `.env.example`
