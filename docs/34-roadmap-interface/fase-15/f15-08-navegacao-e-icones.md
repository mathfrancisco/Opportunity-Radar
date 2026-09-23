# CARD F15-08 — Navegação, orientação e ícones

- **Status:** Backlog
- **Fase:** 15 — Design, consistência e acesso
- **Depende de:** F15-06
- **Bloqueia:** Milestone N
- **Origem no roadmap:** [Roadmap de interface](../../34-roadmap-interface.md), §4

## Resultado

A navegação diz onde o operador está, agrupa as sete telas pelo que elas servem, e continua
utilizável em tela estreita.

## Contexto

`PageShell` rende sete links de texto numa única linha que quebra conforme a largura. O
estado ativo é um sublinhado; em tela estreita, os links viram duas ou três fileiras de
texto solto sobre o cabeçalho, e a identidade visual do produto — um glifo `◉` e o nome —
divide espaço com eles.

As sete telas também não são do mesmo tipo. `Visão geral`, `Oportunidades` e `Candidaturas`
são o trabalho diário; `Empresas`, `Fontes` e `Perfil` são configuração e catálogo;
`Status` é diagnóstico. A navegação plana não conta isso, então a tela mais usada e a
menos usada aparecem com o mesmo peso.

Não há um único ícone na interface. Não é obrigatório que haja, mas hoje toda distinção
entre seções é tipográfica, e uma lista de sete palavras iguais é lida item a item, toda
vez.

## Escopo

- Agrupar a navegação por finalidade, com rótulo de grupo visível ou estrutura equivalente.
- Tornar o estado ativo legível sem depender de sublinhado fino: superfície, peso ou marca.
- Definir o comportamento em tela estreita — barra compacta, menu ou barra inferior — sem
  esconder a tela ativa.
- Criar um conjunto mínimo de ícones inline, um por seção, como apoio ao rótulo e nunca
  como substituto dele.
- Manter `aria-current`, o link para pular ao conteúdo e a ordem de tabulação.

## Fora de escopo

- Biblioteca de ícones de terceiros.
- Menu que esconda a navegação em tela larga.
- Renomear seções ou mudar rotas.

## Notas de implementação

Ícone acompanha o rótulo; nenhum item vira só símbolo. Um ícone sozinho obriga a decorar o
símbolo e é o caminho mais rápido para uma navegação que só o autor entende.

O glifo `◉` é a marca do produto e continua sendo. Se a barra compacta precisar de espaço,
o que cede é o texto do nome, não a marca.

## Critérios de aceite

- [ ] A navegação mostra os grupos, e a seção ativa é identificável sem foco nem hover.
- [ ] Em 360 px a navegação não quebra em mais de duas fileiras, nem esconde a seção ativa.
- [ ] Cada item tem ícone e rótulo; nenhum item é só ícone.
- [ ] `aria-current` continua na seção ativa e o link de pular ao conteúdo continua primeiro
      na ordem de tabulação.
- [ ] Nenhuma rota mudou de endereço.

## Verificação

Percorrer as sete seções em 360 px, 768 px e 1280 px conferindo grupo, estado ativo e
tabulação; confirmar com leitor de tela que a seção ativa é anunciada uma vez.

## Arquivos prováveis

- `apps/web/src/components/PageShell.tsx`
- `apps/web/src/components/`
- `apps/web/src/styles.css`
