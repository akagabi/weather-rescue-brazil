# O teste externo: Radcliffe Observatory, Oxford

Data: 2026-09-07. Artefactos: `bench/g4/external-drybulb.json`,
`bench/g4/external-rain.json`, `profiles/radcliffe-*.json`.

> **Nota (2026-09-11).** Este ficheiro é citado duas vezes no repositório
> (`docs/g4-qc-audit.md` e `data/dataset/README.md`) e **não existia**. Foi
> escrito agora a partir dos artefactos, não de memória — todos os números
> abaixo saem dos dois JSON acima e podem ser reconferidos.

## Porque é que este teste é diferente

Os testes cegos anteriores usam páginas brasileiras, do mesmo arquivo, da mesma
década. Este usa **outro país, outra língua, outro arquivo e outra casa
decimal** — e, sobretudo, uma tabela cuja *semântica está invertida*: nas
tabelas brasileiras as linhas são dias e as colunas são medições; aqui as
**linhas são anos e as colunas são meses**.

Fonte: Internet Archive, `astronomicaland03obsegoog` (domínio público, busca
polite com `scripts/g4_fetch_ia.py`), Tabela II (bulbo seco 1855–1879) e
Tabela IV (chuva 1851–1879). O impresso usa **polegadas e Fahrenheit**, ponto
decimal elevado, e elide a parte inteira (29) imprimindo-a só quando muda
(`30·108`, `29·721`).

O adaptador é o `runs/g4/gen3/epoch2`, treinado em 400 linhas de dois layouts
brasileiros. Nada aqui se lhe parece.

## Resultado

Comparado com as séries publicadas de Oxford (não com uma transcrição nossa —
é por isso que é um teste *externo*):

| Tabela | Células | Na relação | Concordância |
|---|---|---|---|
| Bulbo seco, Tabela II | 276 | 274 | **99,3%** |
| Chuva, Tabela IV | 336 | 306 | **91,1%** |

A "relação" é a que o próprio artefacto ajusta entre o valor impresso e o
publicado (`fitted_centre`), com a dispersão em `mad`. Para a chuva o ajuste é
`0,9818` com `mad` de `0,0227` — ou seja, o impresso e o publicado diferem por
uma constante de escala, e a pergunta é se cada célula cai nessa relação.

### O subconjunto que interessa na chuva

91,1% sobre as 336 células inclui os anos em que os doze meses impressos **não
fecham** no total anual impresso na própria página. Restringindo às linhas que
fecham — que são as únicas onde se sabe que a leitura está internamente
coerente:

**25 linhas × 12 = 300 células, das quais 290 na relação (96,7%).**

É este o número que aparece nos rascunhos de outreach, e é reproduzível a
partir de `bench/g4/external-rain.json` em três linhas: as 25 linhas são as que
satisfazem `sum(jan..dec) ≈ yearly_sum` dentro de 2%, e 25 × 12 dá exatamente as
300 células do denominador citado.

## O que isto estabelece, e o que não estabelece

**Estabelece:** o modelo lê uma tabela de outra publicação, noutra língua,
noutro arquivo, com a semântica de linhas/colunas invertida e outra casa
decimal, sem treino nesse layout — a 99,3% em temperatura e 96,7% em chuva no
subconjunto coerente.

**Não estabelece:** uma taxa de erro para o dataset publicado. Duas coisas
diferem do que é preciso para isso. Primeiro, a comparação é contra séries
publicadas que são elas próprias produto de um processo de redução; uma
divergência pode ser do impresso, do publicado, ou de ambos. Segundo, este
teste **não mede o que o `checks_pass` verifica** — as linhas do Radcliffe não
carregam a aritmética por linha que valida as do Rio de 1883. É uma medida de
leitura, não do tier.

## Onde é que isto falhou primeiro, e o que é que isso ensinou

A primeira corrida deu **0/56** em vez de ~99%. O zero era de *localização*: o
scan tem 898 px de largura para 14 colunas, e o localizador encontrava 4 linhas
de 25 — o modelo lia linhas reais, só que não aquelas que tínhamos rotulado.
Corrigido de forma geral em `wrb.rows` (passo abaixo de `MIN_PITCH_PX` → refazer
a localização com a página a 2× e devolver as caixas na escala original), e
nenhuma página brasileira mudou com isso.

Foi o teste que valeu mais por ter falhado do que teria valido por ter passado:
expôs um limite de resolução que nenhum corpus brasileiro teria revelado.

## Ressalva sobre a janela de sondagem

O localizador procura a coluna do dia numa janela calibrada para as tabelas
brasileiras. Aqui a coluna do ano fica noutro sítio, e o teste só correu
passando `probe_x_frac` explicitamente. **É uma pendência conhecida:** isso
devia ser um campo do perfil, não um argumento — como `table_x_frac` já é.
