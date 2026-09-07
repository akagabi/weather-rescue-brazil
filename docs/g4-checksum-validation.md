# G4.9 — Validação por checksum: testar em escala sem rotular à mão

Data: 2026-09-07. `scripts/g4_checksum_test.py`, `bench/g4/checksum-8-15-gen3.json`.

## A ideia

Algumas tabelas impressas carregam a **própria aritmética**. Nas séries do Rio de 1883, a coluna
`Moyenne` é a média das 7 leituras da linha. Isso permite validar uma página inteira **sem rótulo
humano**: lê-se cada linha e pergunta-se se os números do próprio modelo fecham a conta que o
tipógrafo fez em 1883.

É uma afirmação mais fraca que o gold (uma linha pode errar de um jeito que ainda soma), mas é
**não enviesada, dispensa humano e escala** — que é exatamente o que falta a uma base de evidência
de 38 linhas.

## Resultado (página nunca vista: doc 8 p.15, Janeiro de 1883, 31 dias)

| | |
|---|---|
| Linhas-dia que fecham a conta | **27/29 = 93,1%** |
| Linhas pontuáveis | 29 de 31 |
| Contagem de células emitida | 9 células em 29 linhas (o perfil espera 9) |

As duas falhas são precisamente o que um checksum serve para achar:

- **linha 20**: erra por 0,013 — um dígito final comido;
- **linha 23**: fecharia exatamente se uma célula fosse `19.57` em vez do `12.57` lido. O checksum
  **localizou uma única célula suspeita** para revisão, sem ninguém ler a página.

Descoberta lateral: dada a linha de cabeçalho, o modelo transcreveu os rótulos das colunas
corretamente (`Date | 4 h. M. | 7 h. M. | …`) — a mesma tarefa em que um modelo 2B tinha ido mal
com outro prompt (`bench/g4/header-detection.md`). Vale reaproveitar para criar perfis.

## Por que isto importa para o objetivo maior

Dá para medir generalização em **dezenas de páginas** sem gargalo humano, e o mesmo mecanismo vira
**QC de produção**: toda linha cuja conta não fecha vai para revisão, e o resto entra no dataset
com uma garantia aritmética. É o "somas impressas = checksums grátis" do desenho original do
projeto, agora implementado e medido.
