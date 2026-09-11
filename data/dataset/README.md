# Weather Rescue Brazil — dataset v0.1 (rascunho, não publicado)

Transcrição automática de tabelas meteorológicas impressas do século XIX, lida **offline** por um
modelo aberto de 2B rodando num laptop. Gerado por `scripts/g4_produce.py` com o adaptador
`runs/g4/gen3/epoch2`.

## Conteúdo

| | |
|---|---|
| Linhas | 5.015 (**2.895 utilizáveis**) |
| Valores nas linhas utilizáveis | **34.502** |
| Linhas que são de facto dias | 4.172 — das quais 2.895 aproveitáveis (69.4%); as outras 843 são resumos e linhas de cabeçalho que o localizador captura e o filtro marca |
| Páginas | 192 |
| Estações (linhas utilizáveis) | Imperial Observatório 2.801, Santa-Cruz 230, Corumbá 20, Porto do Maranhão 6, Cuyabá 4 |
| Publicações | Revista do Observatório (1886-91) e **Annales de l'Observatoire Impérial (1883-85)** |
| Período | **1883-01 a 1890-11** (66 meses) |
| **Ausente dos arquivos internacionais** | as 1.194 linhas da v0.1 — ver *Ineditismo* abaixo |

> **Estes números são recalculados, não escritos à mão** (2026-09-11): `scripts/g4_merge.py`
> recontagem a partir do próprio `.jsonl`, e `data/dataset/weather-rescue-brazil.summary.json`
> é gerado por ele. A versão anterior desta tabela dizia 2.708 / 1.862 / 22.548 / 98 páginas e
> estava **duas revisões atrás** do ficheiro que descreve — a tabela de estações vinha de um
> commit e a tabela de cabeçalho de outro.

## Quarta correcção (2026-09-11): uma linha fabricada que passava no tier mais forte

`revista-rio-1886` doc 14 p140 (1886-06) trazia uma linha cujo `raw` é **quinze `1` seguidos**.
Todas as células caíam dentro das faixas declaradas, e uma linha de valores iguais não pode
contradizer a sua própria ordenação — por isso chegou a `checks_pass`, o tier mais forte.

Só a forma da linha a denuncia. Entrou `wrb.qc.degenerate_row` (≥8 colunas numéricas com ≤2 valores
distintos), aplicado em `g4_produce.py` **e** em `g4_rescore.py`. O mesmo defeito em
`revista-santacruz-1889` p24 já era `flagged` — a mesma corrupção tinha dois veredictos diferentes
conforme a página.

As **faixas físicas também estavam largas demais para servir de alguma coisa**: `tmean`/`tmax`/`tmin`
estavam declaradas `[-10, 50]` °C para o Rio de Janeiro, ou seja uma faixa global. Apertadas para
climatologia do Rio (`tmean [12,35]`, `tmin [5,30]`, `humidity [30,100]`, …), mais 9 linhas saíram do
tier utilizável por razões reais (humidade 0,4%, tmin 0,1 °C, evap_sol 40 mm).

**Efeito no total: 3.070 → 3.059 utilizáveis.** Onze linhas, mas onze linhas honestas.

### Quinta correcção (2026-09-11): máximos abaixo do próprio mínimo

Duas linhas de `rio-1883-thermo` (doc 8 p33 e p97) chegaram a `checks_pass` com
`sansabri_max = 7,5` e `sansabri_min = 39,2` — um máximo abaixo do seu próprio mínimo, impossível
para duas leituras do mesmo instrumento. Passaram porque **o check declarado se cala quando a
célula do resultado está vazia**: o perfil verificava `sansabri_oscil = max − min`, e essas linhas
têm a oscilação em branco, então a verificação declinou correr em vez de falhar.

Corrigido com um tipo de check novo, `atleast` ("esta coluna nunca cai abaixo daquela"), que não
depende de nenhuma célula derivada e portanto não tem como se calar. **23 checks `atleast` foram
declarados** nos sete perfis com pares máximo/mínimo (`tmax ≥ tmean ≥ tmin`, `pressure_max ≥
pressure ≥ pressure_min`, `baro_maxima ≥ baro_media ≥ baro_minima`, …).

Verificação de consistência interna do tier utilizável depois disso: **5.345 comparações entre
colunas ordenadas por construção, 0 violações.**

**Efeito no total (com o item seguinte): 3.061 → 2.895 utilizáveis.**

## O que `checks_pass` quer mesmo dizer (releia antes de filtrar)

Continua a valer o que já estava escrito: **`checks_pass` significa "esta linha não se contradiz",
não "esta linha está certa"**. E há agora um número para isso:

| Verificação declarada | Linhas utilizáveis | O que foi de facto verificado |
|---|---|---|
| `mean`/`diff` — aritmética impressa (Annales 1883: barómetro, termómetro, vapor, actinometria) | ~1.900 | a conta que a página afirma sobre si mesma |
| `order` — só a sequência dos dias (Revista Rio + Santa-Cruz, Corumbá, Cuyabá, Maranhão) | ~950 | que os números dos dias formam uma série sensata |

Uma troca entre duas colunas da mesma unidade passa nas duas: ambos os valores continuam plausíveis.
Só um checksum impresso apanha isso — e é por isso que a média mensal impressa (`Mez`) passa a ser
lida: `Profile.verify_month` compara agora o bloco de dias com a linha-resumo da página, usando a
convenção medida por coluna (média para a maioria, máximo/mínimo para os extremos, soma para a chuva
— medido em doc 14 p41, 1886-01).

**Limite honesto:** o localizador quase nunca captura a linha `Mez`. No artefacto de hoje a
verificação corre em **34 linhas** — o resultado fica registado em `monthly_check`, não aplicado ao
veredicto, porque a cobertura ainda não sustenta uma decisão. Para valer para as ~950 linhas de
`order` seria preciso uma passagem dedicada a ler as tabelas-resumo ("Revista climatologica do mez"),
que estão noutra região da página.

## Terceira correcção (2026-09-08): linhas que não são dias

A Revista imprime, na mesma coluna dos dias, um subtotal por década (`Dec.`) e
um total do mês (`Mez`). Em 402 linhas (33,7%) o localizador contou essas linhas
como se fossem dias — doc 16 p.22 devolveu **36 linhas para um mês de 31 dias**.

São médias mensais a passar por observações diárias. **Nenhuma verificação por
linha as pode apanhar**: os números são plausíveis e caem dentro das faixas
físicas. Só a contagem ao nível da página as denuncia.

Corrigido pela leitura, não pela geometria: **o modelo lê o número do dia**, e
os dias formam uma sequência que repete ou avança de um. Fica a maior sequência
consecutiva; o resto não é dia. 114 linhas eliminadas — são os `Dec.` e `Mez`.

A sequência **não precisa de começar em 1**: o localizador falha muitas vezes as
primeiras linhas da página, e dias 4..28 são 25 linhas boas mais uma falha de
cobertura, não 26 linhas más.

| | antes | depois |
|---|---|---|
| utilizáveis | 883 (74,0%) | **835 (69,9%)** |
| valores | 12.406 | **11.909** |
| linhas que não são dias | 0 detectadas | **114 eliminadas** |

## Correcção de proveniência (2026-09-08) — leia isto antes de usar

**37% das linhas da v0.1 estavam atribuídas à estação errada.** 445 linhas
diziam Santa-Cruz quando a página impressa diz Imperial Observatório (415) ou
Corumbá (30). Causa: o perfil confundia *layout* com *estação* — a forma de 15
colunas serve Santa-Cruz **e** o Imperial Observatório a partir de 1888.

Corrigido: cada linha traz agora `station` e `station_source`, lidos da legenda
impressa da página. 1.130 linhas confirmadas pela legenda, 64 continuam
assumidas e dizem-no. Ver `docs/g4-qc-audit.md`.

**Os valores em si estão certos** — as 31 linhas de Dezembro de 1888 reproduzem
a linha `Mez` impressa na própria página em **12 de 12** agregados, com a
pressão máxima e mínima exactas ao centésimo.

## Auditoria de QC (2026-09-08) — leia isto antes de usar

A v0.1 anunciava 954 linhas utilizáveis e um nível `checks_pass` descrito como
"a aritmética da própria página fecha". **Nenhuma linha tinha isso**: os quatro
perfis declaravam `checks: []`, portanto nenhuma aritmética foi alguma vez
verificada. Auditado e corrigido — ver `docs/g4-qc-audit.md`.

Foi declarada a única aritmética que estas linhas de facto carregam, uma
restrição exacta: `minimo <= media <= maximo`. Uma média impressa fora do seu
próprio mínimo e máximo é impossível, não é um caso limite.

| verdict | antes | depois |
|---|---|---|
| `checks_pass` | 0 | **868** |
| `qc_clean` | 954 | 15 |
| `flagged` | 240 | **311** |

71 linhas que saíam como utilizáveis afirmavam uma ordenação impossível e agora
estão sinalizadas com o motivo. O dataset encolheu 7,4% e ficou mais honesto.

**`checks_pass` significa "esta linha não se contradiz", não "esta linha está
certa".** O teste externo contra Oxford (`docs/g4-external-oxford.md`) mostra o
limite: o checksum apanha uma linha invertida, mas fica calado num erro de um
dígito que ainda respeite a ordem.

## Ineditismo

A versão anterior deste README dizia "85 linhas nunca digitalizadas". **Estava
errado, e errado para menos.** O número saiu de uma suposição conservadora, não
de uma verificação. A verificação foi feita depois, contra as fontes primárias:

- **GHCN-Daily** (NOAA, arquivo diário global): baixado o inventário de estações
  (`ghcnd-inventory.txt`, 782.552 linhas), filtrado por prefixo `BR`. Registros
  brasileiros anteriores a 1900: **zero**. O mais antigo começa em **1901**.
- **EMERLAC** (Domínguez-Castro et al. 2017, *Scientific Data*; coleção no
  PANGAEA doi:10.1594/PANGAEA.871490), o resgate de referência dos registros
  instrumentais antigos da América Latina: **14 séries brasileiras**, a mais
  recente terminando em **dezembro de 1856**. Nenhuma estação chamada Santa
  Cruz, Corumbá, Maranhão ou Rio Grande do Sul.

Ou seja: os dados diários brasileiros entre **1857 e 1900** estão essencialmente
ausentes dos arquivos internacionais. Este conjunto cobre 1885–1890 e cai dentro
dessa lacuna. A lacuna não é acidental — o Observatório do Rio fundou a primeira
rede meteorológica brasileira em 1886, e a *Revista do Observatório* é a
publicação dessa rede.

**O que não foi verificado**, e portanto não é afirmado: o ISPD v4 (banco de
pressão à superfície) exige login para a lista de estações, então a pressão
especificamente não foi conferida; e a verificação cobriu arquivos
internacionais, não acervos nacionais brasileiros (INMET), que podem guardar
digitalizações que nunca saíram do país.

## Formato

Uma linha JSON por linha de tabela:

- `values_as_printed` — **o que está impresso**, sem correção silenciosa;
- `values` — o mesmo, com as convenções da publicação desfeitas em código (barômetro com os
  milhares repostos), determinístico e reversível;
- `markers` — palavras que a página imprime no lugar de um número (`Gottas`, `Inap.`), preservadas;
- `verdict` — `checks_pass` (a aritmética da própria página fecha) / `qc_clean` (tudo dentro das
  faixas físicas) / `flagged` (motivo registrado em `problems`, `range_violations`, `check_failures`);
- `padded_trailing` — a leitura veio com uma célula a menos e assumiu-se que a ausente é a última.
  **É uma suposição, marcada e não escondida**;
- procedência completa: `archive`, `item`, `page`, `period`, `row`, `profile`, `source`.

Consumidor que quiser só o subconjunto garantido: filtre `verdict != "flagged"` e, se quiser ser
estrito, `padded_trailing == false`.

## Qualidade

Medida contra o gold humano e testes cegos (`docs/g4-blind-summary.md`): 88–99% de acerto por
célula conforme o layout, com 100% dos números numa página inteira do Maranhão verificada à mão.
Nesta produção, **240 linhas ficaram sinalizadas em vez de entrar erradas** — o comportamento
desejado.

## Limitações conhecidas (honestas)

- **82 linhas do Rio 1886** trazem uma célula `null` a mais entre nebulosidade e chuva: o modelo
  percebe ali uma divisória que o perfil não declara. É consistente, então é uma questão de perfil,
  não de leitura. Elas estão sinalizadas.
- **24 linhas** produziram saída degenerada (sequências como `1 | 2 | 3 …`) em linhas de cabeçalho
  ou de resumo mensal; sinalizadas.
- Nada aqui passou por revisão humana linha a linha. O gold congelado (9 páginas) **não** faz parte
  deste arquivo — é conjunto de avaliação.
- Ainda não exportado para SEF/C3S; é o passo seguinte antes de qualquer publicação.

## Proveniência e direitos

Imagens: Biblioteca Digital de Obras Raras do Observatório Nacional, via DocVirt (sem CAPTCHA,
acesso público). Obras de 1886–1890, domínio público no Brasil (Lei 9.610). A atribuição do acervo
acompanha cada página baixada em `data/raw/docvirt/*/*.json`.

### Sexta correcção (2026-09-11): 164 linhas impossíveis no tier mais forte

Encontrada pela primeira verificação **contra a imagem da página** — a que faltava. A faixa do
barómetro do `rio-1883-barometre` era `[700, 800]`: admitia 717 mmHg, que a 0° e ao nível do mar no
Rio é 956 hPa, fisicamente impossível. **308 das 989 linhas** com média mensal caíam entre 700 e 729,
separadas das 676 reais (750–780) por um **vazio entre 730 e 749**. Uma pressão real não é bimodal
com um buraco de 30 mmHg.

A leitura está certa — a página de Abril de 1883 imprime mesmo `17.56` onde a de Novembro imprime
`57.56` (ambas fiéis: `17.56 → 717.56`, `57.56 → 757.56`, e a linha `Mois` da própria página de
Abril diz 16.9). É uma inconsistência **da fonte**, não do pipeline: o projecto leu-a fielmente e
cumpriu a convenção "nunca corrigir em silêncio". O que faltava era a faixa recusar 717.

Faixa corrigida para a banda física real `[740, 790]` (e a do `vapeur`, que é tensão de vapor e não
pressão, de `[0,40]` para `[5,30]`).

**Efeito: 164 linhas saíram do tier utilizável — 163 que eram `checks_pass`.** Total: 3.059 → 2.895.

### Primeira verificação contra a imagem (2026-09-11)

Amostra estratificada de 19 páginas / 297 linhas do tier utilizável, lida contra as imagens. Foi ela
que encontrou a correcção acima. Nas páginas verificadas linha a linha até agora — `revista-santacruz-1889`
doc 15 p44, entre outras — **os valores batem com o impresso em todas as colunas**, incluindo duas
anomalias que a própria página imprime (`tmax 20,2` com `tmin 22,8` nos dias 5 e 10) e que o dataset
registra fielmente como `flagged`.

A amostra **não** está completa: 19 páginas é o suficiente para ter encontrado isto, não para
declarar uma taxa de erro. A verificação Linha-a-linha das restantes está por fazer.

### Sétima correcção (2026-09-11): o dia que ficou por resolver

`resolve_dittos` existe em `wrb.profile`, com teste, desde o trabalho dos perfis — e **nunca foi
chamado no caminho de produção**. A página de Corumbá imprime dois lançamentos por dia e escreve o
número do dia só no primeiro, como sinal de repetição (`»`) no segundo. Resultado: **31 das 62
linhas daquela estação publicavam `day: "»"`**, 12 delas no tier utilizável. Um consumidor não tinha
como saber de que dia eram.

Encontrado pelo Gabriel a ler a app de verificação, não pelo código nem pelos checks — nenhum
check podia apanhá-lo, porque `»` era tratado corretamente em todo o lado *excepto* no que saía no
ficheiro.

Corrigido: a resolução entra em `values` (convenções desfeitas em código) e o `»` impresso fica em
`values_as_printed`, que tem de continuar fiel ao papel. 36 linhas resolvidas, os 31 pares da página
passam a concordar no dia, e **nenhum veredicto mudou** — o `»` nunca afectou os tiers.

O Gabriel descreveu também a geometria da tabela, que não estava escrita em lado nenhum: a sequência
é `1 às 10, 1 às 4, 2 às 10, 2 às 4`, e as duas colunas de temperatura alinham-se a linhas
diferentes — a máxima do dia na linha das 4h, a mínima da noite na linha das 10h. É a razão pela qual
a pauta escalonada faz um leitor humano hesitar sobre a que linha pertence um valor.
