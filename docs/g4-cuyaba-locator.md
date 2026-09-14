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

## Instrumentado: porque é que afinar parâmetros não resolve

Medido em `15/76` (2026-09-14). **Não há um parâmetro errado; há uma estratégia
errada para esta página.**

**(1) A cadeia desfaz-se por tolerância, não por cabeçalho.**
`CHAIN_GAP_RANGE = (0.8, 1.2)` exige que centros consecutivos distem do passo
entre ±20%. Com passo 22 isso é 17,6–26,4 px — e **apenas 26 dos 49 intervalos
reais caem nessa banda**; os intervalos medidos vão de 14 a 47 px. A passo
apertado, o centróide de tinta oscila mais do que a tolerância permite, e a
cadeia parte-se em pedaços de 3 a 8 linhas.

**(2) Alargar a tolerância move a falha, não a resolve.** Com o intervalo
alargado, a melhor cadeia devolve 11, 12, 22, 29 ou 41 linhas conforme o valor
— e começa em y=674, 1180 ou 202, ou seja **em sítios diferentes a cada
tentativa**. Isto diz que o problema não é o limiar: é o **conjunto de picos**,
que não é estável nesta página. Afinar um parâmetro aqui é escolher qual falha
preferimos.

**(3) A tentativa a 2× tira à página a estrutura de que ela depende.**
`horizontal_rules` encontra **2 regras a 1× e 1 a 2×**. O construtor de cadeia
usa as regras para decidir onde uma cadeia começa e acaba; a tentativa que
existe para *salvar* a página degrada exactamente o sinal de que a página
precisa.

## O que uma tentativa futura deve fazer

**Usar o oráculo do número do dia — e não a geometria — para ancorar as linhas
desta página.** O mecanismo já existe e já foi provado no projecto: foi
construído para os Annales (`DayOracle` em `g4_build_dataset.py`,
`MlxDayOracle` em `g4_run_pages.py`), e a nota do projecto descreve-o como
*"localização guiada por oráculo em cada página: os números de dia impressos
decidem, a geometria apenas propõe"*. Esta página reúne quatro condições que
derrotam a geometria ao mesmo tempo — passo de 22 px abaixo do `MIN_PITCH_PX`,
oscilação de centróide de ±50%, cabeçalho de três níveis, e linhas `Doc.`/`Mez`
— e é exactamente para isso que serve decidir pela leitura em vez do desenho.

Não vale a pena mexer mais em limiares globais: `MIN_PITCH_PX` e
`CHAIN_GAP_RANGE` estão calibrados para 192 páginas que funcionam, e esta
página não é um caso de afinação.

**E olhar para a página em cada passo.** Três vezes nesta sessão se inferiu a
partir de geometria em vez de olhar, e as três vezes a inferência estava
errada — a última levou a correr o modelo sobre seis páginas que nunca tinham
sido abertas.

## Prioridade

**27 páginas `Resumo`** estão neste caso, mais 5 `Redução` e 30 por
identificar, todas já em disco. É o maior conjunto de dados por explorar que
existe no projecto — mas também o mais difícil, e não vale a pena mexer-lhe sem
olhar para as páginas uma a uma.
