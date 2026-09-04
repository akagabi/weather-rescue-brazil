# G4.6 — Teste de generalização: o modelo lê um layout que nunca viu?

Data: 2026-09-04. Custo: R$ 0. Resultado: **negativo no critério principal, com um achado
específico e acionável.** Arquivos: `scripts/g4_test_holdout.py`,
`bench/g4/corumba-holdout.json` (verdade lida à mão, commitada ANTES de perguntar ao modelo),
`bench/g4/holdout-smoke{4,5}.json`.

## 1. O teste

Página de Corumbá (DocVirt 16/72): **layout genuinamente inédito** — 62 linhas (duas leituras por
dia, 10h e 4h), **16 colunas impressas**, instrumentos que não existem na Revista (Fortin,
Aneroides, Hygrometro Saussure, Psychrometro) e quatro colunas de texto livre. Nunca esteve em
treino nem no gold.

Dois modelos, ambos treinados só na Revista:
- **smoke4** — alvo de esquema fixo (as 14 colunas semânticas da Revista);
- **smoke5** — alvo "livre de esquema": a linha **como impressa**, célula a célula, incluindo o
  número do dia e o texto (`wrb.local_model.row_target_printed`).

## 2. Números

| | Gold da Revista (3.822 células) | Corumbá: valores lidos (ignorando posição) | Corumbá: posicionalmente correto |
|---|---|---|---|
| smoke4 (esquema fixo) | **99,08%** | 50% | 3,1% |
| smoke5 (livre de esquema) | **98,95%** | **77%** | 6,2% |

Duas leituras honestas:
1. **Tornar o alvo genérico não custou nada em casa**: 98,95% vs 99,08% no gold (5 células de
   3.822).
2. **A leitura transfere; o alinhamento não.** Em Corumbá o smoke5 recuperou 77% dos valores
   impressos, incluindo as quatro colunas de TEXTO (`fraco`, `c,n`, `annuv.`, `encoberto`) cujo
   vocabulário não aparece em nenhuma linha de treino. Mas a acurácia posicional é ~0.

## 3. A causa, exata

**Os dois modelos emitiram exatamente 15 células. A tabela tem 16.** 15 é o número de células do
layout Santa-Cruz, que é 91% dos dados de treino. O modelo **aprendeu a contar células a partir do
treino, não a partir da imagem** — e uma célula a menos desloca tudo o que vem depois, o que zera
qualquer pontuação por posição.

Dizer a contagem no prompt ("esta linha tem exatamente 16 células") **não resolve**: o modelo
continua emitindo 15 (testado; a acurácia até cai um pouco). A contagem está nos pesos, e o modelo
nunca foi treinado para obedecer a esse tipo de instrução.

## 4. O que isso implica para o objetivo maior (arquivo brasileiro)

Duas rotas, e a escolha é do owner:

**A. Um adaptador por corpus (o que já existe e funciona).** Cada nova publicação custa algumas
centenas de linhas rotuladas e uma tarde de treino: 31,8% zero-shot → 99% com 792 linhas. Já
entregue, já medido, já publicável. Escala linearmente com o número de formatos.

**B. Leitura por CÉLULA (a arquitetura que generalizaria de verdade).** Cortar a linha em células
usando as réguas verticais detectadas e pedir ao modelo uma célula por vez. Aí a estrutura é 100%
geométrica, o modelo faz só OCR de uma célula minúscula, e **nenhuma contagem pode ser
memorizada** porque cada chamada vê uma célula. Funciona em qualquer tabela com réguas,
independente do número de colunas.
- A favor: é a resposta para "ler o arquivo inteiro"; saída de ~5 tokens por célula em vez de 80
  por linha, muito paralelizável.
- Risco real: depende de **detecção confiável de colunas**. A primeira tentativa
  (`wrb.synth.column_gaps`) fechou o número certo de colunas em apenas 1 de 5 páginas testadas.
  Esse é o problema a resolver antes de qualquer retreino.

**Recomendação:** banca-se A agora (está pronto e é um resultado real), e trata-se B como a próxima
fase — de preferência já com um SEGUNDO corpus com verdade humana em mãos, para poder *medir*
generalização em vez de inferi-la de uma página.

## 5. Reprodução

```
python scripts/g4_test_holdout.py --adapter runs/g4/smoke5/epoch2 --printed
python scripts/g4_test_holdout.py --adapter runs/g4/smoke4/epoch2
```
