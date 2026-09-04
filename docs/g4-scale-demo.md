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
| Páginas processadas / aceitas / recusadas | 37 / 35 / **2** (16/38 e 16/39: poucos números de dia lidos; vão para revisão humana) |
| Tempo total | 68 min |
| **Throughput** | **32,5 páginas/hora** (≈ 116 s/página: 24 s localização + 91 s leitura de 28–31 linhas + <0,1 s montagem) |
| Gold, pipeline completo (9 páginas, 3.822 células) | **99,08%** — idêntico à avaliação por linha; a localização não custou acurácia |
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

## 4. Extrapolação honesta

| Corpo | Páginas | Neste M4 (32,5 pág/h) | Custo API (≈US$ 0,04/pág, sem contar 429) |
|---|---|---|---|
| Revista (feito) | 37 | 68 min | US$ 1,5 (gasto real) |
| 1.000 páginas | 1.000 | ~31 h (1,3 dia) | ~US$ 40 |
| Arquivo INMET, ordem de 50.000 | 50.000 | ~64 dias em 1 M4; ~13 dias em 5 Macs; ou 1 GPU L4 alugada em ~2–4 dias | ~US$ 2.000 + limite de taxa |

Throughput é o gargalo a atacar, não a acurácia: 91 dos 116 s por página são a leitura
sequencial linha a linha (3,3 s/linha). Lotes de linhas (batching no MLX), leitura em página
inteira pelo mesmo modelo, ou o oráculo do dia feito pelo próprio leitor (economiza o 2º modelo)
são os três caminhos óbvios; nenhum foi tentado ainda. A outra chave, fora da engenharia, continua
sendo o **acesso institucional às imagens** (INMET/ON).

## 5. Reprodução

```
python scripts/g4_run_pages.py --model runs/g4/mlx-smoke4-q8            # todas as 37 páginas, ~70 min
python scripts/g4_run_pages.py --model runs/g4/mlx-smoke4-q8 --pages 14/22,15/60
python scripts/g4_eval_mlx.py --model runs/g4/mlx-smoke4-q8              # gold por linha, 273 linhas
```
Conversão: `python -m mlx_vlm.convert --hf-path runs/g4/merged-smoke4 --mlx-path runs/g4/mlx-smoke4-q8 -q --q-bits 8`
(`merged-smoke4` = base + adaptador `models/g4/qwen35-lora-smoke4-epoch2` via `merge_and_unload`).
