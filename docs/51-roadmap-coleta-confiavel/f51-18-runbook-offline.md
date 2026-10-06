# F51-18 — pacote de evidência e gate offline do piloto

> Frescor é derivado somente de `SourceRun` completa, `SUCCEEDED`, não-backfill e dentro da
> janela. Timestamp declarativo de inventário e backfill recente não renovam frescor.

Este runbook descreve a janela proposta de sete dias e o relatório offline
`evaluate_rollout_evidence`. O validador é determinístico sobre o JSON recebido; ele não
coleta telemetria, autentica assinaturas, inspeciona CI/worker, realiza backup ou restaura
banco. Um resultado `go` significa apenas que os campos fornecidos satisfazem as regras
locais, não que as observações foram verificadas.

## Manifesto a preencher durante uma janela aprovada

Registrar início/fim UTC, commit e URL/SHA/resultado literal do CI, SHA e digest imutável
da imagem realmente em execução, versão do coletor/parser, configuração não secreta,
coorte elegível congelada, política de exclusão e responsáveis. Para cada fonte registrar
agenda e tentativas, cooldown/indisponibilidade, três `SourceRun` completos distintos e
seus IDs, horários, gatilho e status. Runs de backfill não contam. Uma falha recente não
renova frescor. O pacote não deve conter segredos.

Para cada fonte, fornecer numerador/denominador de descrições úteis e de recall humano.
Recall requer amostra revisada que inclua oportunidades elegíveis publicadas e descartadas;
exclusões precisam de anotação humana. Descrição útil, recall, frescor até sete dias e
terminalidade IA usam população observada, não campos ausentes tratados como zero. Denominador
vazio ou ausente é N/D e produz no-go. IA terminal pode incluir sucesso ou falha terminal;
terminal não significa sucesso.

`scripts`/módulos não assinam decisão. Após preencher o pacote, executar o validador puro
em código local e guardar o JSON de entrada, saída e hashes:

```python
from datetime import UTC, datetime
import json
from opportunity_radar.operations.rollout_gate import evaluate_rollout_evidence

evidence = json.load(open("rollout-evidence.json", encoding="utf-8"))
report = evaluate_rollout_evidence(evidence, now=datetime.now(UTC))
print(json.dumps(report, indent=2))
```

Go requer janela observada de pelo menos sete dias completos, encerrada até o instante de avaliação; manifesto e coorte congelados com versões do coletor/parser;
SHA e digest do CI iguais ao runtime, URL presente;
três inventários completos e distintos por fonte, dentro da janela e com horário; descrição útil e recall ≥95%; frescor
dentro de sete dias; e terminalidade IA de 100% para a população informada. Qualquer N/D,
coorte vazia, incompatibilidade ou denominador inválido bloqueia. F51-14/15/16 podem ficar
adiados e não alteram o gate do núcleo.

## Limite operacional

Backup, restauração e rollback seletivo precisam ser demonstrados apenas em ambiente
isolado `_test`, com escopo e hashes comparados. Este runbook não executa nem declara essas
provas. Também não produz decisão assinada, não habilita fontes/flags, não agenda backfill
e não muda tráfego. Qualquer uma dessas ações depende de aprovação operacional e evidência
real preenchida por responsável autorizado.
