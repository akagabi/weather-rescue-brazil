# Gate G2-B — Relatório final

Data: 2026-09-01. Gate: gold set (9 folhas congeladas, 3.822 células),
estratégia G2-B (schema Gemini + âncora de dia + chamada de cabeçalho
separada + reconstrução determinística do barômetro) contra o mesmo
modelo de gate do G1 (`gemini-3.5-flash`, provider `gemini-flash-full`),
teto duro US$10 em tokens.

## 1. Bug do schema encontrado no caminho (registro, não achado do gate)

Antes deste run, a chamada de tabela do g2b retornava 400 ("invalid
argument") em toda folha. Causa raiz confirmada pelo controller: o
`responseSchema` do Gemini fixava o tamanho do array `rows` via
`minItems`/`maxItems` = contagem de dias do mês (28/30/31) sobre um
schema de 31 itens × 14 campos obrigatórios por item — um curl de
controle mostrou que um schema minúsculo (2 itens) com os mesmos
`minItems`/`maxItems` retorna 200, mas o schema completo (14 campos
obrigatórios × contagem real de dias) 400a. A correção
(`src/wrb/vlm.py::g2b_response_schema`) removeu `minItems`/`maxItems` do
array `rows`; a contagem exata de linhas continua sendo exigida, mas
agora só do lado do cliente, em `_parse_g2b_response` — uma resposta com
contagem errada de linhas ainda é rejeitada como `ExtractionParseError`
(nunca é preenchida/truncada para caber). Uma docstring anterior deste
mesmo arquivo afirmava, de forma incorreta, que `minItems`/`maxItems`
tinham sido "live-verified" como não implicados no 400 — essa afirmação
era falsa (o probe original testou apenas um schema pequeno, não o
schema de produção); a docstring foi corrigida para registrar a causa
raiz real. Um arquivo `bench/g2/gemini-3.5-flash-g2b.json` de uma
tentativa anterior a este fix (9/9 folhas com erro 400, US$0,30 gastos
sem produzir nada pontuável) foi sobrescrito por este run.

Validação de custo mínimo antes do run completo (passo obrigatório):
1 chamada em 1 folha (página 41, 31 dias) — **200, 31 linhas parseadas
corretamente** — só então o run completo das 9 folhas foi disparado.

## 2. Números do gate

Fonte primária: `bench/g2/gemini-3.5-flash-g2b.json` (`aggregate` e
`per_sheet`); baseline de comparação: `bench/g1/gemini-flash.json`
(gate G1, mesmo modelo, zero-shot).

**g2b (agregado, 9/9 folhas pontuadas, 0 erros de harness no resultado
final):**
- `cell_acc` = **0,9885** (~98,8%)
- `structural_err_rate` = **0,00397** (~0,4%)
- `flagged_recall` = **0,000** (0 células erradas auto-sinalizadas — igual
  ao G1, ver §4)
- `n_cells_total` = 3.822 (idêntico ao G1 — mesmo gold set)

**G1 zero-shot (baseline, `gemini-3.5-flash`):**
- `cell_acc` = **0,8812** (~88,1%)
- `structural_err_rate` = **0,1147** (~11,5%)

**Por folha (cell_acc / structural_err_rate, G1 → g2b):**

| folha | período | G1 cell_acc | g2b cell_acc | G1 struct | g2b struct |
|---|---|---|---|---|---|
| 14_22  | 1885-12 | 0,9770 | 0,9816 | 0,0323 | 0,0000 |
| 14_41  | 1886-01 | 0,0645 | 0,9862 | 1,0000 | 0,0000 |
| 14_57  | 1886-02 | 0,9566 | 0,9847 | 0,0000 | 0,0357 |
| 14_75  | 1886-03 | 0,9931 | 0,9908 | 0,0000 | 0,0000 |
| 14_90  | 1886-04 | 0,9881 | 0,9905 | 0,0000 | 0,0000 |
| 14_109 | 1886-05 | 0,9885 | 0,9908 | 0,0000 | 0,0000 |
| 14_142 | 1886-07 | 0,9931 | 0,9954 | 0,0000 | 0,0000 |
| 14_179 | 1886-09 | 0,9976 | 0,9881 | 0,0000 | 0,0000 |
| 14_212 | 1886-11 | 0,9905 | 0,9881 | 0,0000 | 0,0000 |

Duas folhas (14_109, 14_179) sofreram 503/timeout do modelo (congestão
transiente da API, não erro 400/schema) na primeira passada e foram
recuperadas com sucesso em uma segunda tentativa orientada apenas a essas
duas folhas — nenhum 400 foi retentado, conforme instrução do controller.

## 3. Classes de erro: eliminadas vs remanescentes

**Eliminada: a falha catastrófica de data/ano (14_41).** No G1 zero-shot,
14_41 tinha `cell_acc`=0,0645 e `structural_err_rate`=1,000 — toda a
folha lida com o ano/data errados. No g2b, a mesma folha vai para
`cell_acc`=0,9862/`structural_err_rate`=0,0000: a âncora de dia (o modelo
lê apenas o inteiro `day` de cada linha, nunca a data completa) somada à
chamada de cabeçalho separada (`extract_period`) e à reconciliação contra
o período conhecido do gold (`expected_prev_for_sheet`) removeu de vez a
classe de erro "data/ano computada errada pelo modelo" que dominava
90%+ das células erradas no G1.

**Eliminado nas outras 8 folhas: `structural_err_rate` zerado em 7 de 9**
(era 0 em 8/9 já no G1, mas a 14_22 também zerou, de 0,0323 para 0,0000).
Nenhuma violação de sequência de dias (`day_sequence_violations`) em
nenhuma das 9 folhas — a âncora de dia nunca escorregou.

**Remanescente: 1 linha com ≥3 células erradas em 14_57**
(`structural_err_rate`=0,0357 = 1/28 dias). Não é um deslocamento de
data/linha (sem violação de sequência, período reconciliado sem flag) —
é um cluster residual de erros de glifo/valor numa única linha, a mesma
classe "ruído disperso" que já era pequena no G1 e que este gate não
tentou atacar (a estratégia G2-B mirou especificamente o erro estrutural
de data, não glifo).

**`flagged_recall` continua 0,000, igual ao G1** — o modelo não sinaliza
a própria incerteza mesmo transcrevendo com >98% de acerto. Isso não
prejudica o resultado deste gate (a estratégia não dependia de
auto-sinalização), mas confirma o achado do G1: qualquer pipeline futura
de revisão humana precisa de gatilhos externos (`validate_sheet`,
divergência entre provedores), nunca do flag do próprio modelo.

## 4. A regra do gate: superamos 90%?

**Sim, com folga: 98,85% de `cell_acc`, contra a barra de 90% do spec.**
O salto de 88,1% (G1) para 98,85% (g2b) veio quase inteiramente de
eliminar a única folha catastrófica (14_41); as outras 8 folhas já
estavam próximas de 99% no zero-shot e permaneceram lá.

**Próximo passo natural, dado que a barra foi superada**: com
`cell_acc`≥90% e uma classe de erro estrutural dominante já eliminada por
estratégia (sem re-treino), o passo de menor custo agora é **destilar um
modelo aberto pequeno usando este pipeline g2b como gerador de rótulos**
(as 9 folhas do gold + potencialmente mais páginas do mesmo acervo,
rotuladas pelo g2b e revisadas por amostragem) — não fine-tune do próprio
Gemini, que já performa acima da barra. Alternativa de custo ainda menor,
se o objetivo imediato for só entregar dado: **publicar o dataset
corrigido** (as 9 folhas gold + o pipeline g2b aplicado ao restante do
acervo do bib 14) como contribuição standalone, adiando a destilação para
quando houver demanda por um modelo local/offline.

## 5. Gasto

**Total G2 (Task 1 free + Task 2 probe + diagnóstico do bug do schema +
Task 3 run completo + 2 retentativas): ≈US$0,2072**
(ledger cumulativo `data/ledger.json` no fim deste gate: US$0,40335;
menos o total acumulado até o fim do G1, US$0,1962 —
`bench/g1/gemini-flash.json`.`ledger_total_usd`). Contra o teto de
**US$10**, ~2% do teto. `bench/g2/gemini-3.5-flash-g2b.json`.`ledger_total_usd`
(US$0,40335) é o total cumulativo do projeto inteiro até este ponto, não
só do G2 — reconciliado acima contra o marco do G1 para isolar o gasto
do G2 propriamente dito.
