# Relatório do gate G4 — modelo offline (G4.0 → G4.4)

Data: 2026-09-04. Branch `g4-offline-model`. Custo total do G4: **R$ 0** (tudo no M4 de 16 GB).
Plano: `docs/superpowers/plans/2026-09-02-weather-rescue-brazil-g4-offline-model.md`.
Detalhes de construção e da noite de treinos: `docs/g4-data.md`, `docs/g4-model-choice.md`.

## 1. Resultado (o número que decide)

Avaliação nas **9 páginas gold congeladas (3.822 células, triplamente verificadas por humanos)**,
pipeline completo por linha (localização → recorte → modelo → 14 células), métrica = célula
exatamente igual (vazio tem de ser vazio). Recomputado independentemente pelo controlador a partir
das predições commitadas (`bench/g4/*-final-gold.json`) contra o `data/g4/gold_manifest.json`.

| Leitor | Células certas | Acurácia | Linhas no formato |
|---|---|---|---|
| **Modelo local: Qwen3.5-2B + LoRA r=16 (smoke4)** | **3.787 / 3.822** | **99,08%** | 273/273 |
| Modelo local: adaptador smoke2 | 3.780 / 3.822 | 98,90% | 273/273 |
| Referência: API Gemini g2b, consenso n=3 (G3) | — | 99,06% | — |
| Referência: API Gemini g2b, single-shot (G2) | — | 98,85% | — |
| Piso: Qwen3.5-2B zero-shot, por linha | — | 31,8% | 31/40 |
| Piso: tesseract | — | 1,8% | 22/183 |

Por página (smoke4): 22: 97,7 · 41: 99,8 · 57: 99,0 · 75: 98,9 · 90: 99,5 · 109: 98,9 · 142:
99,3 · 179: 99,8 · 212: 99,1. Erros restantes (35): evaporação à sombra 8, ao sol 7, umidade 4,
nebulosidade 4, força do vento 3, barômetro máx 3, resto ≤2 — glifos pequenos das colunas da
direita, mesmo perfil do residual da API.

**Régua do plano: ≥ ~95% com o QC existente = SHIP.** 99,08% empata com o teto do método
(consenso da API, 99,06%). Recomendação: **SHIP como motor offline** (G4.5).

## 2. Como chegou lá (honesto)

| Run | Receita | Gold (recortes da época) | Gold (recortes finais) |
|---|---|---|---|
| smoke1 | 609 linhas reais, 1 época | 80,4% (6 págs) | — |
| smoke2 | + hint de layout por volume, vol. 14 ×4, 2 épocas | 84,8% (6 págs) | **98,90%** |
| smoke3 | + vol. 14 ×8, augmentação, 3 épocas | 95,7% (9 págs) | 99,08% |
| smoke4 | receita do smoke2 nos dados reconstruídos | 95,4% (9 págs) | **99,08%** |

O salto de 85% para 99% **não foi o modelo, foi a geometria**: os recortes de linha derivavam
meia linha na borda direita (deskew grosseiro numa janela estreita; numa página, um artigo acima da
tabela zerava a estimativa fina), e o modelo lia as células da linha vizinha. Três correções, todas
determinísticas e em `src/wrb/rows.py` / `scripts/g4_build_dataset.py`:
1. deskew fino por correlação dos perfis de linha entre uma janela à esquerda e uma nas colunas
   vapor/umidade, medido só no corpo da tabela (duas passagens);
2. localização dirigida pelo oráculo: o localizador só propõe candidatos; um VLM local lê o número
   do dia impresso em cada um e a linha d vai para o candidato que lê d (928 de 1.065 dias lidos
   diretamente; o resto interpolado com checagem de espaçamento);
3. verificação: páginas "ok" pela heurística mas deslocadas 2–3 linhas foram pegas pela leitura do
   dia e recusadas/refeitas.

A mesma deriva contaminava rótulos de treino em ~12 páginas; o rebuild final tem 792 linhas de
26 páginas (recusadas 16/38 e 16/39, poucas leituras diretas).

## 3. O que este número NÃO diz

- É acurácia de **leitura por linha com a geometria acertada**; a localização das linhas é parte
  do pipeline e falhou em 2 de 37 páginas (recusa honesta, vão para revisão humana). No G4.5 a
  demo de escala tem de reportar a taxa de páginas recusadas, não só a acurácia das aceitas.
- O oráculo do número do dia usa um segundo VLM (Qwen3-VL-2B) na localização; no pacote offline
  o próprio modelo treinado pode fazer essa leitura, mas isso ainda não foi medido.
- Os 0,9% restantes são erros de glifo em colunas pequenas, **não auto-flagáveis** (mesma lição
  do G3): o QC externo + revisão humana continua sendo o que leva a >99,5%.
- O dev split (2 páginas dos vols. 15/16) mudou de recortes entre builds; números de dev não são
  comparáveis entre runs. Só o gold é a régua.
- Rótulos de treino vêm da API Gemini (opção A, decisão do owner 2026-09-03); proveniência a
  declarar no model card.

## 4. Custo e reprodutibilidade

- Compute: R$ 0. M4 16 GB, ~45 min por época de ~900 linhas; ~5 s/linha na inferência sem
  otimização (≈ 2,5 min/página). Meta do G4.5: < 1 min/página com GGUF/MLX.
- Adaptadores commitados em `models/g4/` (smoke4 e smoke2, ~20 MB cada) com logs de treino.
- Reproduzir: `scripts/g4_build_dataset.py` → `scripts/g4_train.py --model qwen35 --run X --epochs 2
  --oversample --save-every 20 --eval-gold` → `scripts/g4_eval_adapter.py --adapter runs/g4/X/epoch2`.
- Guarda de vazamento passou em todos os builds e launches (hash do manifesto no log).

## 5. Decisão pedida ao owner

SHIP para G4.5: empacotar (GGUF ou MLX), medir páginas/hora e taxa de recusa em 100+ páginas,
custo por página US$ 0, e escrever `docs/g4-scale-demo.md`. Complemento não técnico já apontado
no plano: acesso institucional a imagens (INMET/ON) para a escala do século.
