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
