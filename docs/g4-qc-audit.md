# Auditoria de QC do dataset v0.1 — o que "utilizável" realmente garantia

Data: 2026-09-08. Motivo: o teste externo em Oxford (`docs/g4-external-oxford.md`)
mostrou que o checksum da própria página pega erros que a faixa física deixa
passar. Isso levantou a pergunta óbvia sobre os dados brasileiros, onde **não
existe Oxford nenhum**: quantas das 954 linhas "utilizáveis" tinham de facto
alguma aritmética verificada?

## Achado

**Nenhuma.** Os quatro perfis de produção declaravam `checks: []`.

Consequências, todas verificadas no ficheiro publicado:

| | |
|---|---|
| Linhas com verdict `checks_pass` | **0** de 1.194 |
| Linhas com `check_failures` não vazio | **0** |
| Linhas "utilizáveis" | 954, **todas** `qc_clean` |

O README anunciava `checks_pass` como o nível mais forte — "a aritmética da
própria página fecha para esta linha". **Nenhuma linha jamais o teve.** O
`qc_clean` assentava só em duas coisas: o parser produziu o número esperado de
células, e os valores caem dentro da faixa física. Nada mais.

## Por que não havia aritmética a declarar

Testei empiricamente as relações candidatas contra as 1.194 linhas:

| relação | dentro de 0,05 |
|---|---|
| `tmean = (tmax+tmin)/2` (Santa-Cruz) | 8,7% |
| `pressure = (pmax+pmin)/2` (Santa-Cruz) | 18,5% |
| `baro_media = (fortin+aneroides)/2` (Corumbá) | 35,5% |

Não fecham porque **a "média" impressa é a média das leituras do dia**, e as
leituras não estão na linha. O checksum que funcionou no Rio-1883 (`Moyenne` =
média das 7 leituras impressas) e em Radcliffe (soma anual = soma dos 12 meses
impressos) não tem equivalente aqui.

## O que havia, e passou despercebido

Uma restrição **exacta**, que não precisa de tolerância nenhuma:

```
minimo <= media <= maximo
```

Uma média impressa fora do seu próprio mínimo e máximo não é um caso limite, é
impossível — a célula está mal lida, com certeza. Exemplos reais que iam no
dataset marcados como utilizáveis:

```
p41 row22:  pressure = 706.56  fora de [755.56, 757.62]   (5 lido como 0)
p142 row5:  baro min = 700.37  com max 763.45 e media 762.02
p142 row20: baro max = 795.72  com media 764.47
```

Declarado como novo tipo de check (`order`) em `wrb.profile.verify`, e aplicado
aos quatro perfis. **Custo de compute: zero** — cada linha guarda o texto bruto
do modelo, então bastou re-pontuar (`scripts/g4_rescore.py`).

## Efeito no dataset

| verdict | antes | depois |
|---|---|---|
| `checks_pass` | 0 | **868** |
| `qc_clean` | 954 | 15 |
| `flagged` | 240 | **311** |
| utilizáveis | 954 (79,9%) | 883 (74,0%) |
| valores utilizáveis | 13.441 | 12.406 |

**O dataset encolheu 7,4% e ficou melhor.** 71 linhas que eram publicadas como
utilizáveis afirmavam uma ordenação fisicamente impossível; agora estão
sinalizadas com o motivo. E 868 linhas passaram a ter uma garantia aritmética
real, onde antes havia zero.

## O que isto ainda NÃO garante

O check de ordenação só olha três células de cada vez. Uma leitura errada que
mantenha a ordem continua a passar — foi exactamente o que Oxford mostrou:
o checksum apanhou a linha invertida de 1863, mas ficou calado em erros de um
dígito que ainda somavam. **Um verdict `checks_pass` significa "esta linha não
se contradiz", não "esta linha está certa".**

A verificação mais forte disponível para a Revista continua por fazer: cada mês
traz uma tabela-resumo impressa ("Revista climatologica do mez"), e a média das
nossas linhas devia bater com ela. É um check ao nível da PÁGINA, não da linha,
e não precisa de modelo nenhum — só de ler as tabelas-resumo.

## Segundo achado: 37% das linhas atribuídas à estação errada

Data: 2026-09-08, mesma sessão. A verificação ao nível da página (abaixo) falhou
de forma estranha — a pressão saía com um desvio **constante** de −3,3 mmHg — o
que não parece erro de leitura, e não era.

A página 15/22, rotulada `revista-santacruz-1889` no worklist, está encimada por
**"Resumo das observações meteorologicas feitas no Imperial Observatorio no mez
de Dezembro de 1888"**. É o Rio, não Santa-Cruz. O desvio constante era a
diferença de altitude entre as duas estações.

Verificadas as 39 páginas do dataset contra a legenda impressa: **15 páginas,
445 linhas (37,3%)**, atribuídas à estação errada.

| | |
|---|---|
| 415 linhas | rotuladas Santa-Cruz, na verdade Imperial Observatório |
| 30 linhas | rotuladas Santa-Cruz, na verdade Corumbá |

### A causa é de desenho, não de digitação

O perfil confundia **layout** com **estação**. `revista-santacruz-1889` nunca foi
"Santa-Cruz": é a **forma impressa de 15 colunas** da Revista, que Santa-Cruz usa
e que o Imperial Observatório passou a usar em 1888 (em 1886 usava a de 16
colunas, com duas colunas de evaporação). Como a forma é a mesma, a transcrição
saiu perfeita — só o nome estava errado.

**É por isso que os valores estão certos e a proveniência estava errada.** Para
dados climáticos a estação não é um detalhe: define altitude, latitude e a
comparabilidade da série.

### Correcção

- cada linha do dataset passa a ter `station` e `station_source`, lidos da
  **legenda impressa da página**, não do id do perfil;
- 1.130 linhas têm a estação confirmada pela legenda; 64 continuam assumidas do
  worklist porque a legenda não foi legível, e dizem isso;
- os perfis passaram a chamar-se pelo layout que descrevem.

| estação (corrigido) | linhas |
|---|---|
| Imperial Observatório, Rio de Janeiro | 842 |
| Observatório de Santa-Cruz, Rio de Janeiro | 235 |
| Corumbá, Mato Grosso | 92 |
| Porto do Maranhão, Maranhão | 25 |

## Verificação ao nível da página: a transcrição em si passa

Cada página da Revista imprime a sua própria linha de resumo mensal (`Mez`).
Comparando as 31 linhas diárias transcritas de Dezembro de 1888 com a linha
`Mez` impressa **na mesma página**:

| coluna | agregado | nosso | impresso | dif |
|---|---|---|---|---|
| pressão | média | 755,61 | 755,63 | −0,02 |
| pressão máx | máx | 762,45 | 762,45 | **0,00** |
| pressão mín | mín | 746,88 | 746,88 | **0,00** |
| temp média | média | 26,20 | 26,10 | +0,10 |
| temp máx | máx | 36,00 | 36,00 | **0,00** |
| temp mín | mín | 17,60 | 17,60 | **0,00** |
| tensão vapor | média | 18,36 | 18,30 | +0,06 |
| humidade | média | 73,19 | 73,60 | −0,41 |
| vento força | média | 3,41 | 3,40 | +0,01 |
| nebulosidade | média | 5,50 | 5,10 | +0,40 |
| evaporação | soma | 106,00 | 106,90 | −0,90 |
| ozone | média | 2,42 | 2,50 | −0,08 |

**12/12.** É o equivalente brasileiro do teste de Oxford, e passa inteiro. O
problema do dataset v0.1 nunca foi a leitura — foi aquilo que dizíamos sobre ela.

## Terceiro achado: 402 linhas que não são dias

Ao testar o localizador na estação nova (Cuyabá), reparei num campo que já
estava gravado no dataset e que nenhum verdict usava: `page_rows_located_ok`.

**402 linhas (33,7%) vêm de páginas cuja contagem de linhas não fecha com os
dias do mês.**

```
doc 16 p22 1889-12: 36 linhas localizadas, 31 dias no mês  (+5)
doc 14 p41 1886-01: 34 linhas localizadas, 31 dias no mês  (+3)
doc 14 p142 1886-07: 33 linhas localizadas, 31 dias no mês (+2)
```

A causa está à vista na própria página: a Revista imprime, **na mesma coluna dos
dias**, um subtotal por década (`Dec.`) e um total do mês (`Mez`). O localizador
conta-os como dias.

São **médias a passar por observações diárias**. E o ponto importante: nenhuma
verificação por linha as pode apanhar — os números são plausíveis, caem dentro
das faixas físicas e respeitam `min <= media <= max`, porque *são* médias
legítimas. Só a contagem ao nível da página as denuncia.

303 destas linhas saíam marcadas como utilizáveis.

### Correcção

Nenhuma linha de uma página cuja contagem não fecha pode ser `utilizável`.
É conservador de propósito: perde-se linha boa junto com a má, porque não
sabemos *quais* das 34 linhas são os 31 dias.

| | antes | depois |
|---|---|---|
| utilizáveis | 883 (74,0%) | **580 (48,6%)** |
| valores utilizáveis | 12.406 | **8.233** |

**O dataset perdeu um terço e é a primeira versão em que "utilizável" quer
mesmo dizer alguma coisa.** As três correcções desta sessão foram todas na mesma
direcção: menos linhas, afirmações verdadeiras.

## Estação nova (Cuyabá): o que falhou e porquê

Perfil criado (`cuyaba-1889`, 14 colunas, incluindo **altura das águas do Rio
Cuyabá** — série hidrológica diária que nenhuma outra publicação do corpus tem).

O localizador falha em 4 das 5 páginas. Diagnóstico, não palpite: as linhas
**não têm passo constante**. A coluna de texto livre "Estado do céo" quebra
linha, empurrando os números do dia seguinte, e os intervalos reais medem
61, 65, 212, 87, 73 px. Todo o `_chain_for_pitch` assume passo constante.

Adicionado `locate_rows_by_runs`: em vez de periodicidade, usa os **corridos de
tinta da coluna do dia**, filtrados por largura (um dia é 1-2 dígitos, ~10 e
~20 px; `Dec.`, `Mez` e as réguas ocupam quase toda a coluna). Só aceita uma
janela que devolva a contagem **exacta**.

**Resultado honesto: 1 das 5 páginas.** A detecção automática da coluna do dia
devolve larguras entre 42 e 74 px nas cinco páginas da mesma publicação, e o
filtro por largura não sobrevive a isso. Fica por resolver; a via provável é o
perfil declarar `day_x_frac`, como já teve de declarar `probe_x_frac` para
Oxford.
