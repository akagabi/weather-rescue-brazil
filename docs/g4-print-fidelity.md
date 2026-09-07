# G4.8 — O segundo teste cego achou um erro meu: alvos não fiéis ao impresso

Data: 2026-09-07. Achado por: `bench/g4/blind-rio1883-gen1.json`.

## O sintoma

Segundo teste cego, primeira **publicação diferente** (não a Revista): Rio de Janeiro, Novembro de
1883, cabeçalho em francês, 9 colunas (`profiles/rio-1883-vapeur.json`). Resultado: **30/45 =
66,7%** — muito pior que os 99,3% do Maranhão. O padrão dos erros era gritante:

| impresso | modelo leu |
|---|---|
| 15.32 | **75.32** |
| 14.09 | **74.09** |
| 14.11 | **765.11** |

O modelo estava **inventando um 7 na frente** das primeiras colunas numéricas.

## A causa (erro meu na montagem do treino)

Os rótulos vindos da API já traziam o **barômetro com os milhares reconstruídos**: a página da
Revista imprime `58.36`, o rótulo dizia `758.36`. Como o alvo de treino era o rótulo, o modelo
aprendeu **“nas primeiras colunas, acrescente 7”** — uma convenção da Revista — e aplicou isso a
uma tabela de tensão de vapor de 1883, onde não faz sentido nenhum.

Isso também contraria a convenção declarada do próprio projeto: **fiel ao impresso, nunca correção
silenciosa**. A reconstrução tem de acontecer **depois**, em código (`restore_thousands`), não
dentro do alvo do modelo.

## A correção

`wrb.profile` ganhou o par:

- `Column.elided` + `Column.elided_range` — declara que a coluna é impressa sem os dígitos da
  frente e em que faixa o valor real vive;
- `Profile.to_printed(values)` — desfaz a convenção **antes de escrever o alvo de treino**;
- `Profile.from_printed(values)` — repõe os dígitos **depois da leitura**, via `restore_thousands`.

Round-trip verificado: `758.36 → 58.36 → 758.36`. Os alvos de Santa-Cruz agora começam em
`54.88 | 55.94 | 53.78`, que é o que está impresso na página.

## Por que isso importa além do bug

O teste cego numa publicação diferente **detectou uma contaminação de domínio que nenhuma métrica
interna pegaria**: no gold da Revista o modelo contaminado marca 99%, porque lá a convenção vale.
Só uma tabela de outra publicação, com outra faixa de valores, revelou que ele tinha aprendido uma
regra do corpus em vez de aprender a ler.

**Lição para o método (vale para o paper):** qualquer transformação específica do domínio aplicada
aos rótulos vira comportamento aprendido e viaja com o modelo. Alvo de treino = o que está
impresso. Convenções = código, depois.
