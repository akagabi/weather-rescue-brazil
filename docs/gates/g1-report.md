# Gate G1 — Relatório final

Data: 2026-09-01. Gate: gold set (9 folhas congeladas, 3.822 células) vs 2
VLMs Gemini zero-shot, teto duro US$10 tokens.

## 1. Números do gate

Fonte primária dos agregados: `bench/g1/gemini-flash.json` (`aggregate`) e
`bench/g1/gemini-flash-lite.json` (`aggregate`); taxonomia e comparação
por-folha: `bench/g1/errors.md`; narrativa e reconciliação: `task-11-report.md`.

**`gemini-3.5-flash` (flash cheio, gate primário)** — `bench/g1/gemini-flash.json`:
- `cell_acc` = **0,8812** (~88,1%)
- `structural_err_rate` = **0,1147** (~11,5%)
- `flagged_recall` = **0,000** (0 de 454 células erradas auto-sinalizadas)
- 9/9 folhas pontuadas, 0 erros de harness

**`gemini-flash-lite-latest` (comparação)** — `bench/g1/gemini-flash-lite.json`:
- `cell_acc` = **0,8506** (~85,1%)
- `structural_err_rate` = **0,2442** (~24,4%)
- `flagged_recall` = **0,0085** agregado macro por folha (1 de 571 células
  erradas no total bruto, ≈0,0018 — as duas leituras coexistem, ver
  `bench/g1/errors.md` §"duas denominadores")
- 9/9 folhas pontuadas, 0 erros de harness

**`gemini-flash-latest` (modelo mandado pelo controller): indisponível.**
503 persistente ("high demand") confirmado de forma independente três
vezes — dois `curl` diretos horas apart, uma tentativa dedicada de 8
tentativas/60s de backoff pelo próprio harness, e um teste direto do
coordenador (`task-11-report.md` §"gemini-flash-latest is unavailable").
`gemini-3.5-flash` (estável, não-`-latest`, confirmado em
`/v1beta/models` e via `curl` com imagem) assumiu o papel de gate cheio no
lugar dele; troca de volta é de uma linha em `vlm.py` se a Google resolver
o outage.

**Lite vs cheio, por folha** (`bench/g1/errors.md` tabela §"Per-sheet
scores"): o flash cheio vence em **7 de 9 folhas**, empata com o lite na
pior folha compartilhada (14_41 — ambos 0,065/1,000, falha de ano na data,
não de tabela) e conserta de forma dramática a pior folha exclusiva do
lite: **14_179 vai de 0,790/0,967-estrutural no lite para 0,998/0,000 no
cheio** — o cheio aplica corretamente a regra de reconstrução do dígito
elidido do barômetro em toda linha; o lite a abandona após a linha 1. A
única folha onde o lite ganha é 14_57 (0,974 vs 0,957 — o cheio tem zero
linhas estruturais ali, mas alguns glifos a mais).

## 2. Gasto

**Total: US$0,1962** (`bench/g1/gemini-flash.json`.`ledger_total_usd`,
consistente com `task-11-report.md`), contra o teto de **US$10** — 2% do
teto. Composição: US$0,0872 na corrida do lite
(`gemini-flash-lite.json`.`ledger_total_usd`, confere com 16 chamadas ×
US$0,00545 em `data/ledger.json`) + US$0,1090 no trabalho do flash cheio
(20 chamadas × US$0,00545 em `data/ledger.json`), dos quais uma fração —
a sondagem do outage do `gemini-flash-latest` e uma corrida abortada
antes de gravar resultado — foi **gasto perdido** em chamadas que nunca
produziram nada pontuável. `task-11-report.md` não fornece o valor exato
desse desperdício; reconciliando `data/ledger.json` (20 chamadas
`gemini-flash-full` cobradas) contra as 9/9 folhas efetivamente pontuadas
na corrida final (uma cobrança por `extract()`, sem custo extra por
retry, por `task-11-report.md` §"Cap caveat"), **11 das 20 chamadas (≈
US$0,060) não correspondem à corrida pontuada** — essa é a estimativa
verificável de gasto perdido, não os ~US$0,049 citados de memória em
versões anteriores deste relatório. Gasto perdido, mas dentro do teto por
uma margem enorme e documentado, não escondido.

## 3. Achados que moldam o G2 (o valor real deste gate)

**Erro dominante é ESTRUTURAL e CONCENTRADO, não ruído de OCR espalhado.**
90,7% das 571 células erradas do lite (518 células — `bench/g1/errors.md`
§"Whole-dataset error-bin counts") vêm de só duas falhas de folha inteira:
o campo de data com ano (e no lite, também mês) trocado em **14_41**, e a
regra de reconstrução do dígito de milhar do barômetro **largada após a
linha 1** em **14_179** (lite; o flash cheio resolveu essa). Erros de
glifo isolados são só ~7% das células erradas (~1% de todas as células) —
a leitura célula-a-célula já é boa. Isso é diagnosticável, e provavelmente
atacável por **estratégia** (âncoras de linha/coluna, extração por linha,
verificação de cabeçalho de período) tanto quanto por fine-tune — o
problema não é "o modelo não sabe ler dígitos", é "o modelo não aplica a
convenção estrutural da página em toda linha".

**O modelo quase nunca sinaliza a própria incerteza.** `flagged_recall`
~0 nos dois modelos: 1 de 571 células erradas no lite (0,0018 bruto,
`bench/g1/errors.md` §Finding 1), **0 de 454 no flash cheio, em todas as 9
folhas**. A instrução explícita do prompt (regra 1: sinalizar
ilegível/incerto) é seguida essencialmente nunca, mesmo quando o valor
está visivelmente errado. **A revisão humana do G2 não pode confiar na
confiança auto-reportada do modelo** — precisa de gatilhos externos
(checksums do mez impressos, faixas físicas via `validate_sheet`,
divergência entre provedores), não do flag do próprio modelo.

**Faithful-vs-normalize: o modelo "corrige" o que devia transcrever
fielmente.** O gold set preserva de propósito 9 células (5 folhas) onde o
valor impresso é fisicamente impossível, fiel ao fac-símile mesmo contra a
instrução explícita do prompt (regra 2: não adivinhar/corrigir valor
impossível). **5 de 9 (56%) foram silenciosamente "corrigidas" pelo
modelo** apesar da instrução (`bench/g1/errors.md` §Finding 2, tabela).
Duas batem **digit-for-digit** com palpites que o próprio curador do gold
já havia testado e rejeitado (765,72 e 2,7 — ambos registrados em
`gold/SELECTION.md`/notas do curador como "corrigido anteriormente ...
revertido"). Nenhuma das 5 veio com flag de incerteza. Isso confirma, com
evidência real e não hipotética, exatamente o modo de falha que a
convenção fiel-ao-impresso do gold foi desenhada para capturar — e é, por
si, um achado publicável: instrução explícita no prompt não basta para
suprimir a normalização silenciosa de um VLM.

## 4. Aplicação da regra do gate + recomendação

Regra do spec (`2026-08-31-resgate-met-historico-design.md`, linha G1):
**≥90% célula com incerteza sinalizada → destilação direta (G2-A)**;
**<90% mas com erros diagnosticáveis → fine-tune mira o diagnóstico
(G2-B)**; **erros difusos sem caminho barato → KILL** (gold sobrevive como
contribuição independente).

**Resultado: 88,1% < 90%.** Mas os erros não são difusos — são
**concentrados em 2 de 9 folhas, com causa raiz identificada e nomeada**
(campo de data / regra de reconstrução de dígito elidido), e a
`flagged_recall` seria irrelevante de qualquer forma já que nenhum dos
dois modelos sinaliza incerteza de forma útil. Isso é o caso
"diagnosticável", não o caso "difuso sem caminho barato".

**Recomendação: G2-B — fine-tune/estratégia dirigido ao erro estrutural.
Não KILL, não destilação direta.**

Não destilação direta porque 88,1% < 90% e a `flagged_recall` (0,000 no
modelo de gate) não dá base de incerteza utilizável para uma pipeline que
dependa de auto-triagem do modelo destilado. Não KILL porque o erro tem
causa raiz nomeada e concentrada em duas classes de falha estrutural, não
espalhada célula a célula — exatamente o cenário em que o spec pede
fine-tune dirigido, não abandono.

**Esboço do que o G2 tentaria primeiro** (ordem de custo crescente):
1. Estratégia sem re-treino: extração por linha com âncora de coluna
   fixa + verificação de cabeçalho de período (mês/ano) contra o texto da
   própria folha antes de aceitar a data — ataca 14_41 e a família de
   "column shift" (14_90, 14_57, 14_142 dia 14) sem gastar em fine-tune.
2. Prompt reforçado especificamente para a regra do dígito elidido do
   barômetro (repetir a âncora a cada N linhas, não só na linha 1) —
   ataca a classe 14_179 diretamente.
3. Se estratégia não fechar a lacuna: fine-tune supervisionado com o gold
   como target, focado nas duas classes estruturais dominantes (não em
   glifo, que já está bom).
4. Gatilho de revisão humana baseado em `validate_sheet` (faixas físicas,
   checksums do mez), nunca no flag do próprio modelo.

**Custo estimado**: ordem **US$50–150** por spec para fine-tune completo;
provavelmente **bem menos** se o passo 1/2 (mudança de estratégia/prompt,
sem re-treino) já fechar a maior parte da lacuna — vale tentar antes de
gastar no treino.

## 5. Contribuição já garantida, independente do G2

Mesmo que o G2 nunca aconteça, este gate já produziu um artefato
publicável por si: o **gold set triplo-verificado** (9 folhas, 3.822
células, fiel-ao-impresso, congelado — Task 9), o **pipeline aberto** de
fetch/OCR/avaliação (Tasks 2–11), e o **achado normalize-vs-faithful**
acima (evidência concreta e nomeada de que VLMs zero-shot normalizam
silenciosamente valores impressos anômalos apesar de instrução explícita
em contrário). Isso sozinho já é contribuição de dados + achado
metodológico, com ou sem G2.

## 6. Pedido explícito ao Gabriel

Três caminhos, uma escolha:

1. **Aprovar G2-B** — destravar orçamento G2 na ordem US$50–150, com
   aprovação por gasto (não um cheque em branco), tentando estratégia
   antes de fine-tune conforme esboço acima.
2. **Pausar aqui** — entregar gold set + pipeline como contribuição
   publicável, sem seguir para G2 agora.
3. **KILL** — encerrar o pipeline; gold set ainda sobrevive como
   contribuição standalone.

Recomendação deste relatório: **opção 1 (G2-B)**, pelos motivos da seção
4. Decisão é sua.
