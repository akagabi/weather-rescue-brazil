# Verificação contra a imagem

    .venv/bin/python -m wrb.verify_serve      ->  http://127.0.0.1:8766

A ferramenta que faltava. Toda a exactidão deste projecto até aqui foi medida
sobre o **gold congelado** — nove páginas, tripla-verificação, deliberadamente
fora do dataset. Não havia número nenhum sobre as linhas publicadas:
`checks_pass` diz que uma linha não se contradiz, não que bate com o papel.

## O que faz

Uma linha de cada vez: o recorte **que o modelo viu** (`loc.chain`, via
`boxes_for_centres`/`crop_boxes` — o mesmo caminho da produção, porque verificar
um recorte diferente seria julgar algo que o modelo nunca olhou) ao lado dos
valores que o dataset afirma, campo a campo.

`1` certo · `2` errado · `3` pular · `p` página inteira · `⌫` voltar.
O erro corrente aparece no topo. Os julgamentos vão para
`data/verify/verdicts.jsonl`, uma linha de JSON cada, e sobrevivem ao restart.

## A amostra

Estratificada por perfil, **só o tier utilizável e só linhas-dia**: as linhas
`flagged` já se sabe que precisam de revisão, e incluí-las deturparia a
exactidão do tier que um consumidor vai filtrar. Cada perfil entra com pelo
menos uma linha, porque os perfis diferem no que os verifica — aritmética
impressa para os Annales de 1883, só a sequência dos dias para a Revista.

82 linhas, 11 perfis, ~1 min por linha.

## Porque é que isto vinha primeiro

A primeira passagem (19 páginas, 297 linhas) encontrou, na primeira página que
leu, **164 linhas fisicamente impossíveis no tier mais forte** — a faixa do
barómetro admitia 717 mmHg. Ver a sexta correcção em `data/dataset/README.md`.

## Ressalva

Recortes muito largos são fatiados e empilhados (`_tile`): uma linha tem
proporção perto de 30:1, e encolhida para caber na janela os algarismos ficam
ilegíveis — o que anularia o exercício.

O trabalho de verificação da amostra de 19 páginas **não está completo**:
3 páginas lidas linha a linha. A app é para acabar isso e para a amostra de 82.

## Aviso importante (2026-09-11): use a PÁGINA INTEIRA

O recorte da linha é recalculado a cada arranque, a partir do `locate_day_rows`
de hoje. **O localizador responde de forma diferente da que produziu as linhas
da Revista** — em `16/159`, por exemplo, o passo de linha que ele mede hoje é
23 px quando o verdadeiro é ~40 px, e as caixas caem nas linhas erradas.

Consequência: nesses casos o recorte mostra uma linha que **não** é a que os
valores ao lado descrevem, e não avisa. A verificação do Gabriel foi válida
porque ele leu a **página inteira** — a app abre agora nesse modo, com o
recorte da linha como alternância (`p`).

Isto não é um defeito do dataset: as linhas foram produzidas com a geometria
como estava então, e batem com o papel. É um defeito da ferramenta, e a razão
pela qual a reprodutibilidade do recorte está registada como limitação no
`DATASET_CARD.md`.
