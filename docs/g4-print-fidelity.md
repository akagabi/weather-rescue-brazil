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

## Resolução: diversidade de convenção, não só equilíbrio de linhas (gen3)

Corrigir os alvos (gen2) consertou o teste de 1883 **e quebrou o do Maranhão**: o modelo trocou um
viés pelo oposto. gen1 sempre **acrescentava** um 7 que não existe; gen2 sempre **removia** um 7
que existe.

Causa: eu equilibrei **contagem de linhas**, não **exemplos distintos**. gen2 viu 200 linhas
distintas de Santa-Cruz (barômetro sempre elidido) contra 40 distintas de Corumbá (barômetro
sempre por extenso), repetidas ×5. Repetição não acrescenta diversidade.

gen3: 40 distintas de cada convenção, ×5 cada.

| modelo | Maranhão barômetro | Maranhão não-barômetro | Maranhão numérico | 1883 francês |
|---|---|---|---|---|
| gen1 (alvos contaminados) | 72/72 | 192/192 | **100%** | 67% |
| gen2 (fiel ao impresso) | 30/72 | 192/192 | 84,1% | **100%** |
| **gen3 (diversidade equilibrada)** | **69/72** | 184/192 | **95,8%** | **98,4%** (época 2: 99,2%) |

**Em gen1 e gen2 as células NÃO-barômetro são 192/192 = 100%.** O erro inteiro, nos dois casos,
estava numa única convenção tipográfica. Os erros que restam em gen3 são falhas isoladas de linha,
não uma regra sistemática.

### A lição, e é a contribuição metodológica do trabalho

Um modelo pequeno **aprende as convenções de impressão da distribuição de treino** e as aplica onde
não valem. Duas consequências práticas:

1. **Alvo de treino = o que está impresso.** Convenções (dígitos elididos, arredondamentos,
   normalizações) vão em código, depois da leitura.
2. **Equilibre exemplos DISTINTOS de cada convenção**, não linhas. Repetir 40 linhas ×5 não ensina
   variedade.

E o ponto de método que só um corpus múltiplo revela: **no gold da própria Revista, gen1 e gen2
marcam ~99% igualmente.** A contaminação era invisível dentro do corpus de origem. Só duas
publicações diferentes, puxando em direções opostas, tornaram o viés mensurável.
