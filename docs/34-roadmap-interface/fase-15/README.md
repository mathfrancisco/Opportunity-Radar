# Cards da Fase 15 — design, consistência e acesso

Estes cards tratam a dívida visual que a interface acumulou enquanto crescia tela a tela:
cor hexadecimal literal em todo componente, mapa de status duplicado, e um padrão diferente
de carregando, vazio e erro por rota.

A ordem é de baixo para cima: token antes de componente, componente antes de estado,
estado antes de acessibilidade e responsividade.

| Ordem | Card | Depende de |
| --- | --- | --- |
| 1 | [F15-01 — tokens e tema](f15-01-tokens-e-tema.md) | Nenhum |
| 2 | [F15-02 — componentes compartilhados](f15-02-componentes-compartilhados.md) | F15-01 |
| 3 | [F15-03 — estados de carregamento, vazio, erro e conflito](f15-03-estados-da-interface.md) | F15-02 |
| 4 | [F15-04 — acessibilidade e teclado](f15-04-acessibilidade.md) | F15-02 |
| 5 | [F15-05 — responsividade e densidade](f15-05-responsividade.md) | F15-02 |

F15-03, F15-04 e F15-05 podem seguir em paralelo. Os três encerram a fase e liberam o
Milestone N.

## Invariantes da fase

- a Fase 15 muda apresentação, nunca semântica: nenhuma tela passa a afirmar algo novo
  sobre os dados;
- `null` continua sendo exibido como indisponível, e nunca como zero;
- token novo só existe para substituir literal em uso;
- componente compartilhado nasce de duplicação já presente no código, não de previsão.
