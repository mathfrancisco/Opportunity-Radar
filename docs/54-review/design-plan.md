# Plano visual candidato — revisão antes da migração

## Direção

Um espaço de decisão de carreira: silencioso, legível e orientado à comparação. A marca não compete com as vagas. A única assinatura visual é o azul-petróleo, usado como orientação e ação, enquanto estados continuam semânticos.

| Token | Cor | Uso |
| --- | --- | --- |
| Papel | `#F7F8F8` | fundo amplo e neutro |
| Tinta | `#132229` | títulos e texto principal |
| Ardósia | `#52626A` | texto auxiliar e metadados |
| Petróleo | `#0B5D66` | foco, navegação e ação principal |
| Névoa | `#DDE7E7` | divisórias, superfícies selecionadas |
| Sinal | `#A94A17` | prazo e atenção; nunca como marca |

Inter Variable é a família inicial, com `Inter, ui-sans-serif, system-ui, sans-serif` como fallback. Títulos usam 600–650, corpo 15–16 px com entrelinha de 1.5. A leitura principal fica alinhada à esquerda; largura de texto longa é limitada a 72 caracteres.

```
desktop
┌───────────┬────────────────────────────────────────────────┐
│ navegação │ pergunta da página / contexto / ação            │
│ por tarefa├────────────────────────────────────────────────┤
│           │ filtros ou resumo                               │
│           │ conteúdo da decisão: tabela, detalhe ou etapas  │
└───────────┴────────────────────────────────────────────────┘

mobile
┌──────────────────────────┐
│ marca + menu             │
│ pergunta / contexto      │
│ filtros empilhados       │
│ cartões com decisão      │
└──────────────────────────┘
```

A proposta evita o painel administrativo genérico: não há mosaico de métricas decorativas, gradientes, sombras difusas ou uma borda arredondada aplicada a tudo. O inventário de vagas tem linhas precisas e comparáveis; o detalhe usa uma coluna de evidências e uma coluna de decisão. A revisão mostra apenas uma ação primária por contexto.

## Checagem crítica

A primeira proposta poderia ter se parecido com um dashboard SaaS comum se transformasse todos os resumos em cards. A revisão reserva superfícies elevadas para decisões, mantém o Inbox como lista comparável e usa uma faixa lateral de prioridade no lugar de chips ornamentais. O caráter vem da relação entre evidência, tempo e decisão de carreira, não de decoração.

## Medidas de acessibilidade propostas

- Texto `#132229` sobre `#F7F8F8`: 15.2:1; texto `#52626A` sobre `#F7F8F8`: 5.9:1.
- Petróleo `#0B5D66` sobre Papel: 7.2:1; contorno de foco em Petróleo atende 3:1 contra as superfícies claras.
- Botões, links e inputs têm foco de 3 px; controles têm 44 px de altura em mobile.
- Em 320/360 px a navegação e filtros empilham; em 768 px o Inbox muda para cards; em 1280/1440 px a tabela e a coluna de decisão reaparecem.

## Medi��o V3

A medi��o executada est� em `contrast.json`: papel/tinta 15.32:1, papel/slate 5.96:1, papel/petr�leo 7.12:1, branco/petr�leo 7.58:1, foco/papel 7.12:1 e contorno de controle/branco 3.79:1. N�o use os valores como certificado WCAG completo; eles cobrem somente os pares declarados no prot�tipo.
