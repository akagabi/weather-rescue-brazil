# Weather Rescue Brazil — dataset v0.1 (rascunho, não publicado)

Transcrição automática de tabelas meteorológicas impressas do século XIX, lida **offline** por um
modelo aberto de 2B rodando num laptop. Gerado por `scripts/g4_produce.py` com o adaptador
`runs/g4/gen3/epoch2`.

## Conteúdo

| | |
|---|---|
| Linhas | 1.194 (883 utilizáveis, 74,0%) |
| Valores nas linhas utilizáveis | **12.406** |
| Páginas | 39 |
| Estações (corrigido) | Imperial Observatório 842, Santa-Cruz 235, Corumbá 92, Porto do Maranhão 25 |
| Publicações | 4 layouts / 2 obras |
| Período | 1885-12 a 1890-11 |
| **Ausente dos arquivos internacionais** | **as 1.194 linhas** — ver *Ineditismo* abaixo |

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
