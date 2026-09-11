# A leitura em duas escalas não encontra os erros — resultado negativo

Data: 2026-09-11. `scripts/g4_disagree.py`, `scripts/g4_disagree_report.py`,
`data/verify/disagreements.jsonl`. 960 linhas, 32 páginas, o perfil
`revista-santacruz-1889` inteiro.

## O que se tentou

Duas linhas de raciocínio levaram aqui. A primeira é do próprio projecto: um
modelo **não sinaliza a própria incerteza** (`flagged_recall` medido em
**0,000**), portanto a revisão humana tem de ser accionada por algo externo. A
segunda é do G3, onde o cruzamento multi-resolução apanhou **7 de 7** células
erradas conhecidas numa página.

Se um modelo lê a mesma linha duas vezes a escalas diferentes e obtém o mesmo
valor, esse valor é estável; se obtém valores diferentes, uma das duas leituras
está errada. A ideia era que isso produzisse uma lista de suspeitos pequena o
bastante para uma pessoa ler — não 660 linhas, mas um punhado.

**A ideia não funciona, e o teste que a desmente é o único que existe:** o
método foi construído para encontrar exactamente o que uma pessoa encontrou à
mão, e não encontra nenhum dos dois.

| Erro conhecido (encontrado pelo Gabriel) | Duas escalas concordam? |
|---|---|
| `16/159` dia 8, `tmin` 21,16 onde a página imprime 21,3 | **sim — `shifts=[]`, `changed=[]`** |
| `15/166` dia 22, `cloudiness` 0,01 onde a página imprime 0,00 | **sim — `shifts=[]`, `changed=[]`** |

## Porque é que falha

**Porque estes erros são consistentes, não aleatórios.** A escala 2,0 e a
escala 3,0 produzem *o mesmo dígito errado*. Perturbar a leitura não perturba o
erro, e é isso que o método precisaria que acontecesse.

Não é uma surpresa nova: é exactamente o muro que o G3 já tinha encontrado e
registado. O consenso de n=3 votos moveu a API de 98,85% para 99,06% — e o
resíduo que sobra é descrito no relatório como *"erros de glifo consistentes,
o mesmo glifo errado nas três leituras, dentro da faixa, coerente com o
checksum"*. Votar não ajuda quando todas as leituras erram igual. Trocar a
escala também não.

Repetir uma leitura é uma defesa contra ruído aleatório. Este erro não é ruído
aleatório — é o modelo a ler uma célula de forma consistente e errada.

## O ruído, medido

Mesmo que acertasse, o sinal estava enterrado. De 960 linhas:

| | |
|---|---|
| linhas com uma célula que mudou de coluna entre as duas leituras | **227** (23,6%) |
| linhas com uma célula que mudou de valor na mesma coluna | **244** (25,4%) |
| páginas em que a maioria das linhas discorda | **7 de 32** |

Um quarto do dataset não é uma lista de suspeitos; é um quarto do dataset. A
concentração mais forte é `precip` ↔ `evap_sombra` (60 + 52 ocorrências), duas
colunas adjacentes em milímetros onde uma troca deixa os dois valores
plausíveis — interessante como sintoma, inútil como lista de trabalho, porque
`precip` está vazio (`Gottas`, `......`) em mais de metade das linhas, e é
nessas que o modelo escorrega.

## O que isto custa, e o que não custa

**Não custa nada ao dataset.** Nenhum veredicto mudou; nenhum valor mudou. O
artefacto congelado em `version.json` continua o mesmo.

**Custa uma esperança, e vale a pena dizê-la em voz alta:** não há aqui um
caminho automático para o resíduo. As três tentativas desta sessão —
convenção de casas decimais, assinatura de fusão de colunas, e agora
discordância entre escalas — falharam todas, cada uma por uma razão diferente e
agora registada. O que resta é:

1. **Revisão humana**, que é o que encontrou os dois erros, e é o que a
   literatura da área também diz (o gold deste projecto precisou de
   tripla-verificação humana pelos mesmos motivos);
2. **um mecanismo de leitura genuinamente diferente** — outro modelo, outra
   arquitectura — e não a mesma leitura perturbada;
3. **aceitar a taxa de erro declarada**, que é o que o G3 recomendou desde o
   início.

A opção 3 é defensável e é a razão pela qual esta limitação está escrita no
`DATASET_CARD.md` em vez de escondida. A opção 1 é a que escala pior e a única
que se provou. A opção 2 é investigação, não trabalho de acabamento.

## Nota metodológica que fica

A primeira versão do `g4_disagree.py` leu com `g4_run_pages.MlxRowReader`, que
fixa `g4_train.INSTRUCTION` — o prompt de esquema de 14 colunas do caminho
antigo. Isso mapeia uma resposta de 14 células num perfil de 15 colunas, e
todas as células "diferem". Reportou 31 de 31 linhas erradas na primeira
página, por uma razão que não tinha nada a ver com o modelo. O leitor tem de
usar `INSTRUCTION_PRINTED`, o prompt que produziu o dataset.
