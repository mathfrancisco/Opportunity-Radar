# Cards da Fase 15 — design, consistência e acesso

Estes cards tratam a dívida visual que a interface acumulou enquanto crescia tela a tela:
cor hexadecimal literal em todo componente, mapa de status duplicado, e um padrão diferente
de carregando, vazio e erro por rota.

A ordem é de baixo para cima: token antes de componente, componente antes de estado,
estado antes de acessibilidade e responsividade.

| Ordem | Card | Depende de | Status |
| --- | --- | --- | --- |
| 1 | [F15-01 — tokens e tema](f15-01-tokens-e-tema.md) | Nenhum | Concluído |
| 2 | [F15-02 — componentes compartilhados](f15-02-componentes-compartilhados.md) | F15-01 | Concluído |
| 3 | [F15-03 — estados de carregamento, vazio, erro e conflito](f15-03-estados-da-interface.md) | F15-02 | Concluído |
| 4 | [F15-04 — acessibilidade e teclado](f15-04-acessibilidade.md) | F15-02 | Concluído |
| 5 | [F15-05 — responsividade e densidade](f15-05-responsividade.md) | F15-02 | Concluído |
| 6 | [F15-06 — tipografia, espaçamento e elevação](f15-06-tipografia-e-forma.md) | F15-01 | Concluído |
| 7 | [F15-07 — hierarquia da Visão geral](f15-07-hierarquia-da-overview.md) | F15-06 | Concluído |
| 8 | [F15-08 — navegação, orientação e ícones](f15-08-navegacao-e-icones.md) | F15-06 | Concluído |
| 9 | [F15-09 — carregamento sem salto](f15-09-carregamento-sem-salto.md) | F15-03, F15-06 | Concluído |

Os cinco primeiros cobriram a base: cor nomeada, componentes únicos, estados unificados,
acesso por teclado e tabelas que rolam no próprio contêiner.

Os quatro seguintes saíram de uma auditoria feita depois deles, sobre o que ainda separa a
interface de um produto acabado: a forma continua sem escala — tipografia, espaçamento,
raio e sombra são escolhidos por tela —, a Visão geral apresenta oito números com o mesmo
peso sem dizer qual exige ação, a navegação é uma fileira plana de sete palavras, e o
carregamento troca a página inteira por uma faixa de texto que some com um salto.

F15-06 vem antes de F15-07 e F15-08 pelo mesmo motivo que F15-01 veio antes de F15-02:
reorganizar uma tela sem escala declarada é escolher espaçamento na mão outra vez.

## Invariantes da fase

- a Fase 15 muda apresentação, nunca semântica: nenhuma tela passa a afirmar algo novo
  sobre os dados;
- `null` continua sendo exibido como indisponível, e nunca como zero;
- token novo só existe para substituir literal em uso;
- componente compartilhado nasce de duplicação já presente no código, não de previsão.
