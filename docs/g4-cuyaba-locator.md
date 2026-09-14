# Porque é que o localizador falha nas páginas «Resumo» de Cuyabá

Data: 2026-09-14. Não resolvido — isto é o diagnóstico, não a correcção.

## O sintoma

`cuyaba-1889` contribui 92 linhas para o dataset, **88 delas `flagged`**. O
perfil está certo (as 14 colunas correspondem ao impresso). O problema é o
localizador.

Numa página típica (`15/76`, Janeiro de 1889):

| | |
|---|---|
| linhas de dia no impresso | 31 (+ 3 `Doc.`/`Dec.` + 1 `Mez` ≈ 35 linhas) |
| passo de linha real | **~22 px** |
| o que o localizador devolve | 31 centros, dos quais **os primeiros 4 são o cabeçalho** |
| consequência | o índice 4 é o dia 1 → o índice 30 é o dia 27, e **os dias 28–31 nunca são lidos** |

Passo certo, contagem certa, **todas as linhas no lugar errado** — que é o modo
de falha que este projecto existe para apanhar, aqui a acontecer no próprio
localizador.

## A causa, e não é o cabeçalho

`MIN_PITCH_PX = 34.0` em `wrb/rows.py`: *"abaixo disto o perfil de linha é
grosso demais para separar linhas; refazer a 2×"*. O passo real desta página é
**~22 px**, portanto o caminho barato está desenhado para a rejeitar. O
algoritmo tenta então a 2×, e **essa tentativa também não devolve exactamente
31** — cai no último recurso, `locate_rows_by_runs`, que devolve 26 centros
errados.

Os candidatos de passo que a busca experimenta nesta página são
`[31, 63, 22, 54, 42, 75]`; nenhum produz uma cadeia de exactamente 31.

## O que foi tentado e porque foi revertido

Foi acrescentado um campo de perfil `rows_y_frac` (a banda vertical onde as
linhas de dados vivem), com testes — a mesma forma de `probe_x_frac` e
`table_x_frac`. **Não resolve:** com a banda, o último recurso devolve 26 linhas
em vez de 31, porque o problema não é filtrar o cabeçalho, é a busca de passo a
falhar abaixo de `MIN_PITCH_PX`.

Foi revertido. Acrescentar superfície à função mais load-bearing do repositório
— de que dependem 192 páginas — por uma capacidade que não resolve o caso que a
motivou é exactamente o tipo de coisa que não se deve deixar ficar.

## O que uma tentativa futura precisa de fazer

1. Perceber porque a tentativa a 2× não devolve 31 nesta página (o passo a 2×
   seria ~44 px, bem dentro da janela). Instrumentar `_search` a 2× e ver a
   contagem de picos.
2. Só depois decidir se a correcção é uma banda declarada no perfil, um
   `MIN_PITCH_PX` menor, ou outra coisa.
3. **Verificar contra a imagem em cada passo.** Três vezes nesta sessão se
   inferiu a partir de geometria (regularidade do passo) em vez de olhar para a
   página, e as três vezes a inferência estava errada — a última delas levou a
   correr o modelo sobre seis páginas que nunca tinham sido abertas.

## Prioridade

**27 páginas `Resumo`** estão neste caso, mais 5 `Redução` e 30 por
identificar, todas já em disco. É o maior conjunto de dados por explorar que
existe no projecto — mas também o mais difícil, e não vale a pena mexer-lhe sem
olhar para as páginas uma a uma.
