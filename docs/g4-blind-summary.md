# G4 — Evidência cega acumulada: quatro layouts, duas publicações

Data: 2026-09-07. Modelo: Qwen3.5-2B + LoRA (`runs/g4/gen3/epoch2`), **treinado em dois layouts,
400 linhas, no M4, R$ 0**. Nenhum dos layouts abaixo estava no treino.

| # | layout | colunas | linhas testadas | como foi verificado | resultado |
|---|---|---|---|---|---|
| 1 | Revista, Rio 1886 | 16 | 30 | gold humano triplamente verificado | 90,7% |
| 2 | Porto do Maranhão 1886 | 12 | 24 (página inteira) | lido à mão **e** o total mensal de chuva impresso (150,90 mm) fecha | **95,8% numérico** |
| 3 | Rio 1883, tensão do vapor (francês) | 9 | 14 | checksum por linha: Moyenne = média das 7 leituras | **98,4%** |
| 4 | Rio 1883, termômetros | 13 | 28 (página inteira) | **a própria aritmética da página**: Oscil = Max − Min, 2× por linha | **96,4%** |

Duas publicações distintas (Revista do Observatório; Annaes de 1883), duas línguas, contagens de
coluna de 9 a 16, cabeçalhos aninhados, colunas de texto livre e valores textuais (`Inap.`)
dentro de colunas numéricas.

## O que cada teste acrescenta

- **#2** é o mais forte em verdade: 264/264 números certos, e a coluna de chuva **lida pelo modelo**
  soma exatamente o total que o tipógrafo imprimiu em 1886 — o documento validando o modelo.
- **#3** é a primeira publicação diferente, e foi ele que revelou a contaminação de convenção
  (`docs/g4-print-fidelity.md`) — invisível dentro do corpus de origem.
- **#4** é o primeiro teste **sem nenhum rótulo humano**: o perfil declara a aritmética
  (`Profile.checks`) e a página se corrige sozinha. A única linha que falhou apontou um dígito:
  o modelo leu `34.1`, a página imprime `33.1`, e 33,1 − 23,9 = 9,2 fecha.

## Por que isso sustenta a tese do framework

Adaptar a uma publicação nova custa **dezenas de linhas** (`docs/g4-learning-curve.md`: 20 linhas
já dão 92–97%), e **validar não custa nada** onde a tabela declara a própria aritmética. Os dois
juntos são o que torna plausível varrer um arquivo inteiro sem uma equipe de transcritores.

## Limite honesto

Tudo é impresso, brasileiro, das décadas de 1880, do mesmo acervo digitalizado (DocVirt/ON). Uma
varredura de 56 páginas nas outras 12 obras do acervo não achou mais tabelas — são texto corrido.
Um terceiro corpus, de outro arquivo e de preferência não brasileiro, é o próximo passo para a
afirmação valer além disso.
