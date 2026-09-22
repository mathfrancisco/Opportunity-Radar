# CARD F13-01 — Estado persistente dos jobs

- **Status:** Concluído em 2026-09-22
- **Fase:** 13 — Operação contínua
- **Depende de:** Fases 10 e 11
- **Bloqueia:** F13-02, F13-05, F13-06
- **Origem no roadmap:** [Roadmap principal](../../33-roadmap-pos-mvp.md), §§24–26, 30 e risco 7

## Resultado

Cada job funcional do worker tem um estado operacional persistido e consultável,
sem transformar o scheduler em uma fila distribuída.

## Contexto

Jobs mantidos apenas na memória não podem ser avaliados pelo `doctor` após reinício
ou por outro processo. A operação precisa distinguir job saudável, ausente, atrasado
e falho a partir de evidência persistida.

## Escopo

- Persistir por job a última tentativa, último sucesso, última falha, duração e
  próxima execução prevista.
- Registrar a passagem e o resultado dos jobs de coleta, normalização, matching e
  análise, preservando correlation IDs nos logs.
- Derivar atraso a partir do schedule configurado.
- Manter uma única fonte de verdade transacional para o estado observado.

## Fora de escopo

- Fila distribuída, Redis, Celery ou alteração da política de agendamento.

## Notas de implementação

Atualize o estado no início e no encerramento de cada execução. Uma falha não pode
apagar o último sucesso conhecido. O estado representa observação operacional, não a
unidade de trabalho nem um mecanismo de lock.

## Critérios de aceite

- [x] Cada job persiste tentativa, sucesso, falha, duração e próxima execução.
- [x] Reiniciar o worker preserva a evidência anterior.
- [x] Atraso é calculável a partir do schedule persistido.
- [x] Falha de um job não remove seu último sucesso.
- [x] Estado e logs permitem correlacionar uma passada específica.

## Verificação

Execute uma passada bem-sucedida e uma que falha de cada tipo de job; consulte o
estado após reiniciar o worker e confirme os campos e o atraso esperado.

## Arquivos prováveis

- `src/opportunity_radar/worker.py`
- `src/opportunity_radar/*/models.py`
- `src/opportunity_radar/migrations/`
- `src/opportunity_radar/doctor.py`
