# Cards da Fase 14 — cadastro e curadoria pela interface

Estes cards tiram do terminal o que hoje só existe lá: criar uma fonte, homologá-la,
registrar uma vaga avulsa, cadastrar uma empresa e vinculá-la a uma fonte.

A ordem preserva a dependência real de contrato: fonte e vaga usam API que já existe;
empresa e vínculo exigem endpoints novos.

| Ordem | Card | Depende de |
| --- | --- | --- |
| 1 | [F14-01 — cadastro de fonte](f14-01-cadastro-de-fonte.md) | Fase 13 |
| 2 | [F14-02 — homologação e kill switch](f14-02-homologacao-de-fonte.md) | F14-01 |
| 3 | [F14-03 — entrada manual de vaga](f14-03-entrada-manual-de-vaga.md) | F14-01 |
| 4 | [F14-04 — cadastro de empresa](f14-04-cadastro-de-empresa.md) | Fase 13 |
| 5 | [F14-05 — vínculo entre empresa e fonte](f14-05-vinculo-empresa-fonte.md) | F14-04 |

F14-04 pode seguir em paralelo com F14-01. F14-02, F14-03 e F14-05 encerram a fase e
liberam o Milestone M.

## Invariantes da fase

- a tela nunca habilita uma fonte externa sem evidência confirmada, data de revisão, termos
  revisados e collector testado;
- toda escrita concorrente envia a versão esperada e trata o conflito como conflito;
- vaga manual entra por `SourceRun` e `RawItem`, com procedência, e nunca direto em
  `Opportunity`;
- empresa criada pela tela passa pela mesma reconciliação do importador de pesquisa.
