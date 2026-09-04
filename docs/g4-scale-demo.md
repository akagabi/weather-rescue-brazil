# G4.5 — Demo de escala: o motor offline sobre a Revista inteira

Data: 2026-09-04. Máquina: MacBook M4, 16 GB. Rede: **zero chamadas**. Custo por página: **US$ 0**.
Arquivos: `scripts/g4_run_pages.py`, `bench/g4/scale-demo.json` (inclui as 35 planilhas geradas).

## 1. O pacote

| Peça | O que é | Tamanho |
|---|---|---|
| Leitor de linhas | Qwen3.5-2B + LoRA smoke4 fundido, convertido para MLX, **8 bits** | 2,3 GB |
| Oráculo do número do dia | Qwen3-VL-2B-Instruct em MLX (bf16, `mlx-community`) | 4,4 GB |
| Geometria | `wrb.rows` (deskew fino, candidatos de linha), `wrb.dataset` (recortes) | código |
| Pós-processamento | `restore_thousands`, `assemble_sheet`, `qc.flag_violations` (os mesmos do caminho API) | código |

Quantização: 8 bits mantém **99,08%** no gold (igual ao bf16 em torch); 4 bits cai para 97,4%
(`bench/g4/mlx-smoke4-q{4,8}-gold.json`). Escolha: 8 bits.

## 2. Números da rodada (37 páginas, todas as tabelas transcritas da Revista)

| Métrica | Valor |
|---|---|
| Páginas processadas / aceitas / recusadas | 37 / 36 / **1** com lotes (16/38); 35 / 2 sequencial (16/38, 16/39) |
| Tempo total | 29 min (com lotes) / 68 min (sequencial) |
| **Throughput** | **75,6 páginas/hora** com lotes (≈ 49 s/página: 13 s localização + 35 s leitura + <0,1 s montagem). Sem lotes eram 32,5 pág/h (116 s/página). |
| Gold, pipeline completo (9 páginas, 3.822 células) | **99,06%** com lotes / **99,08%** sequencial — a localização não custou acurácia, e lotes também não |
| Concordância com a transcrição da API nas 26 páginas não-gold | 93,9% bruto; **95,5%** com as duas colunas de evaporação fundidas (ver §3) |
| Chamadas de rede / custo | 0 / US$ 0 |

Por página (gold, ponta a ponta): 22: 97,7 · 41: 99,5 · 57: 98,7 · 75: 99,1 · 90: 99,5 · 109:
99,1 · 142: 99,3 · 179: 99,8 · 212: 99,1.

## 3. Onde modelo e API discordam nas páginas não-gold (e quem está errado)

Concordância com a API **não é acurácia**: a API também erra (~1%) e, descobriu-se aqui, é
inconsistente. Três causas, em ordem de tamanho:

1. **Inconsistência de esquema nos rótulos da API (não é erro do modelo).** Santa-Cruz tem UMA
   coluna de evaporação ("á sombra"). A API pôs o valor em `evap_sol` em algumas páginas (ex.
   15/89) e em `evap_sombra` em outras; o modelo é consistente (`evap_sombra`, como o hint de
   layout diz). Fundindo as duas colunas, a concordância sobe de 93,9% para 95,5%. **Ação:
   normalizar isso no dataset publicado (G3 Task 3).**
2. **Dias 10 e 20** concentram 263 das ~460 divergências restantes — as linhas imediatamente
   acima das linhas "Déc." (resumo da década). Ou a API (leitura de página inteira) ou o modelo
   (recorte por linha) escorrega para a linha "Déc." nesses dias. Só a imagem decide: **são os
   candidatos nº 1 para a revisão humana do owner** (~2 células × 2 dias × 26 páginas).
3. **Página 16/18** (81% de concordância) tem um layout com colunas ausentes (barômetro máx/mín
   vazios); o modelo desloca colunas ali. Layout raro, não coberto pelo treino; recusa ou revisão.

Fora isso, o residual é o mesmo do gold: dígitos pequenos nas colunas da direita.

## 3b. Por que 2 min/página e como virou 49 s (medido)

Perfil de uma leitura de linha no M4: 293 tokens de prompt a 493 tok/s (0,6 s de prefill) + 80
tokens gerados a **44 tok/s** (1,8 s). Esses 44 tok/s **são o teto do hardware para UMA sequência
por vez**: decodificação autorregressiva relê os 2,3 GB de pesos a cada token, e o M4 base tem
~120 GB/s de banda de memória — 2,3 GB × 44 = ~100 GB/s, ou seja, saturado.

O gargalo, então, nunca foi o modelo: era a **arquitetura de chamadas**. Uma página fazia ~70
sequências separadas (31 linhas + ~38 leituras de dia do oráculo), cada uma pagando a releitura
inteira dos pesos. A API do Google faz 1 chamada por página, num datacenter.

**Lotes** amortizam essa releitura entre as linhas: 3,3 s → 0,82 s por linha (4×) com acurácia
idêntica (97,70% na página 22, o mesmo número da versão sequencial). Na prática, com os dois
modelos residentes em 16 GB, lotes de 31 estouram o alocador Metal; lotes de 6–8 são o ponto
estável, e o runner reduz o lote sozinho se der erro (`_with_fallback`), grava página a página e
tem `--resume` (um GPU timeout matou uma rodada na página 24 — nada foi perdido).

Folga que ainda existe, em ordem de tamanho:
1. **Matar o oráculo separado** (13 s/página + 4,4 GB de RAM): o próprio leitor treinado pode
   emitir o número do dia junto com as células. Libera memória para lotes maiores, o que acelera
   também a leitura. Estimativa: ~25 s/página.
2. **Saída mais curta**: 80 tokens por linha é o teto atual e quase sempre é atingido.
3. **GPU**: A100 tem 1.555 GB/s contra os ~120 GB/s do M4 (~13×) e comporta lotes muito maiores.

## 4. Extrapolação honesta

| Corpo | Páginas | Neste M4 (32,5 pág/h) | Custo API (≈US$ 0,04/pág, sem contar 429) |
|---|---|---|---|
| Revista (feito) | 37 | 29 min | US$ 1,5 (gasto real) |
| 1.000 páginas | 1.000 | ~13 h | ~US$ 40 |
| Arquivo INMET, ordem de 50.000 | 50.000 | ~28 dias em 1 M4 (ou ~9 dias com o oráculo removido); numa A100 alugada, ~2 dias por ~US$ 200 | ~US$ 2.000 + limite de taxa |

Throughput continua sendo o alvo, não a acurácia (ver §3b). A outra chave, fora da engenharia,
continua sendo o **acesso institucional às imagens** (INMET/ON).

## 4b. Para passar do Google (hoje é empate: 99,06% local vs 99,06% consenso da API)

O residual são 35 células de 3.822, quase todas glifos pequenos nas colunas da direita. Alavancas,
da mais barata para a mais cara:
1. **Auto-consenso**: ler cada linha 3× com temperatura e votar. Foi exatamente o que levou a API
   de 98,85% para 99,06%. Lá custava dinheiro; aqui custa só 3× compute, que com lotes é viável.
2. **Re-leitura multi-resolução** nas células em que o consenso discorda (o flagger do G3 teve
   100% de recall sobre os erros conhecidos).
3. **Rótulos melhores**: a revisão humana dos suspeitos dos dias 10/20 volta para o treino.

## 5. Reprodução

```
python scripts/g4_run_pages.py --model runs/g4/mlx-smoke4-q8            # todas as 37 páginas, ~70 min
python scripts/g4_run_pages.py --model runs/g4/mlx-smoke4-q8 --pages 14/22,15/60
python scripts/g4_eval_mlx.py --model runs/g4/mlx-smoke4-q8              # gold por linha, 273 linhas
```
Conversão: `python -m mlx_vlm.convert --hf-path runs/g4/merged-smoke4 --mlx-path runs/g4/mlx-smoke4-q8 -q --q-bits 8`
(`merged-smoke4` = base + adaptador `models/g4/qwen35-lora-smoke4-epoch2` via `merge_and_unload`).
