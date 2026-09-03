# G4 — Plano de treino do modelo offline: escolha de base, receita, o que precisa e o que custa

Data: 2026-09-02. Estado: PROPOSTA para decisão do owner antes de qualquer gasto.
Plano-pai: `/Users/bueno/detail/docs/superpowers/plans/2026-09-02-weather-rescue-brazil-g4-offline-model.md`.
Todos os números externos abaixo foram verificados hoje por pesquisa com URL; os números locais
foram medidos nesta máquina (M4, 16 GB). Onde é estimativa, está escrito "estimativa".

## 1. Decisão proposta em uma frase

Treinar um **LoRA sobre um VLM de documentos ≤1B (PaddleOCR-VL-1.6, Apache-2.0)** em
**recortes por linha** produzidos pela geometria já existente em `wrb.zoom`, com dados reais da
Revista + tabelas sintéticas renderizadas, avaliar contra o gold congelado, e empacotar via GGUF
ou MLX para rodar no M4. Custo de compute total estimado **< US$ 40** (bem abaixo do teto de
US$ 50–150 já aprovado). A pendência que NÃO é técnica é a de licença (seção 6).

## 2. O que existe hoje (medido)

| Item | Valor |
|---|---|
| Tabelas da Revista transcritas pelo pipeline g2b+consenso | 18 de 38 (`bench/g3/revista-full.json`) |
| Tabelas não-gold utilizáveis como rótulo | 9 |
| Células rotuladas não-gold | 3.466 |
| Gold congelado (só avaliação, nunca treino) | 9 tabelas, 3.822 células |
| Teto quando a Revista terminar | ~29 tabelas não-gold ≈ 12.500 células |
| Imagens já baixadas (docId 14/15/16) | 942 páginas, ~1675×2519 px, ~220 KB webp |
| Formato de saída | `Sheet` = 31 linhas × 14 colunas numéricas (`gold.py`) |
| Código reutilizável sem mudança | `Sheet`, `assemble_sheet` (dia-âncora), `restore_thousands` (barômetro), `validate_sheet`, `qc.flag_violations`, `metrics.score`, `zoom.detect_table_borders` + `row_band_geometry` + `crop_row_bands` |
| Ambiente | `.venv` Python 3.12 com torch 2.14 (MPS ok), transformers 5.16, peft 0.20, trl 1.12, datasets; tesseract no sistema |
| Gasto acumulado G0–G3 | US$ 1,01 |

O ponto que muda o desenho: **12 mil células é pouco para fine-tune de VLM em nível de página
(~29 exemplos)**, mas `crop_row_bands` já transforma cada página em 31 recortes de linha. Em nível
de linha o mesmo corpus vira **~900 exemplos reais** (com a Revista completa), cada um com 14
números, imagem pequena e saída curta. É o que torna o treino viável com o que temos.

## 3. Granularidade: linha, não página (posição, não consenso)

| | Página inteira → JSON | Recorte de linha → 14 números |
|---|---|---|
| Exemplos reais disponíveis | ~29 | ~900 |
| Tokens visuais por exemplo (Qwen-style, 32 px/token) | ~2.900 sem cap | ~200–400 |
| Tokens de saída | ~2.000 | ~60 |
| Estrutura (qual linha é qual dia) | o modelo tem de acertar | vem da geometria determinística + `day` impresso na linha; erro de deslocamento de linha (o erro nº 1 do campo) fica impossível por construção |
| Reuso do pipeline | `assemble_sheet` igual | `assemble_sheet` igual (monta a tabela a partir das 31 leituras) |
| Custo de treino | 10× maior por exemplo | pequeno |
| Risco | overfit em 29 páginas | recorte desalinhado (o G3 já mediu: a zoom crop introduz erros próprios; precisa de margem e validação da geometria por página) |

Recomendação: **linha primeiro**. É a modernização do MeteoSaver (layout determinístico +
reconhecedor aprendido) que o plano-pai já lista como opção (b), só que o "reconhecedor" é um VLM
pequeno em vez de um CRNN, o que dá tolerância a tipografia velha sem projetar uma arquitetura.
Página inteira fica como experimento de comparação, não como caminho principal.

## 4. Modelo base (verificado 2026-09-02)

| Candidato (HF id) | Params / licença | Tipo | Fine-tune | Números publicados | Apple Silicon |
|---|---|---|---|---|---|
| **PaddlePaddle/PaddleOCR-VL-1.6** (2026-05) | 0.9B / Apache-2.0 | VLM de documentos, prompt nativo de tabela | transformers nativo (sem remote code); guia Axolotl QLoRA/full | OmniDocBench v1.6 geral 96,3; Table-TEDS 94,8 (autorrelato) | GGUF+mmproj oficial; `mlx-vlm` suporta `paddleocr_vl` |
| **Qwen/Qwen3.5-2B** (2026) | 2B / Apache-2.0 | multimodal geral | TRL SFTTrainer + PEFT; Unsloth; `mlx-vlm` LoRA no Mac | OmniDocBench 1.5: 80,9 (≈ Qwen3-VL-4B, > Qwen3-VL-2B 65,9) | mlx-vlm sim; GGUF visão não verificado |
| ibm-granite/granite-docling-258M | 258M / Apache-2.0 | VLM de documentos (DocTags) | transformers nativo; treina no próprio M4 | TEDS estrutura 0,97 (IBM) | MLX oficial |
| deepseek-ai/DeepSeek-OCR-2 | ~3,5B total / Apache-2.0 | OCR de documentos | remote code + transformers fixado em 4.46 + flash-attn: atrito com TRL/PEFT | Table TEDS 87,8 | mlx-vlm sim |
| lightonai/LightOnOCR-2-1B | 1B / Apache-2.0 | OCR de documentos | transformers v5, LoRA Colab | sem TEDS de tabela publicado | GGUF; MLX não verificado |
| Two-stage: microsoft/table-transformer + trocr-base-printed | 29M + 0,3B / MIT | grade determinística + reconhecedor | treinado em PDF moderno; precisaria fine-tune próprio em scan de 1886 | — | CPU ok |

Descartados: Qwen3-VL-2B (superado pelo 3.5-2B), Qwen2.5-VL-3B (licença research), Gemma 4
E2B (5,1B total e licença Gemma, ver seção 6), dots.ocr/olmOCR (grandes demais para 16 GB).

**Escolha: PaddleOCR-VL-1.6 como principal, Qwen3.5-2B como hedge.** Motivos: melhor TEDS de
tabela publicado abaixo de 1B; 0,9B cabe folgado no M4 em bf16 (~2 GB) e treina LoRA localmente;
caminho offline mais limpo (GGUF oficial). O Qwen3.5-2B entra se o Paddle for fraco em tipografia
do século XIX, porque segue instrução (JSON direto, "traço = vazio") e tem o ecossistema de
fine-tune mais profundo. Granite-Docling é a terceira rodada barata, não a primeira.

Congelar o encoder de visão nos dois; LoRA só no LM (r=16–32, alvos q/k/v/o + MLP).

## 5. Receita de treino (o que efetivamente rodar)

**Dados (G4.0, R$ 0):**
1. `dataset.py`: para cada tabela não-gold transcrita com sucesso, gerar 31 recortes com
   `crop_row_bands` (com margem extra e uma checagem da geometria: número de bandas escuras ≈ 31,
   senão a página vai para revisão manual e fica fora do treino) e parear cada recorte com a linha
   correspondente do `pred` (14 valores + `day`). Manifesto `data/g4/train_manifest.json` com
   sha256 por imagem.
2. Guarda de vazamento: `assert_no_gold_leakage` falha se qualquer (doc, page) do gold aparecer, e
   compara sha256 dos recortes contra os das páginas gold. Testado.
3. Split dev: 2 tabelas não-gold inteiras separadas (não linhas soltas, para não vazar por página)
   para escolher hiperparâmetros. **O gold nunca escolhe hiperparâmetro**, só dá o número final.
4. Sintético (a peça que segura o treino com pouco dado): renderizar tabelas no estilo da Revista
   com Pillow (fontes serifadas antigas livres, colunas e réguas como nas páginas reais), valores
   sorteados das distribuições por coluna dos rótulos de treino (nunca do gold), e degradação de
   scan (ruído, borrão, rotação ±1°, contraste, sangramento). Alvo: 20–50 mil linhas sintéticas.
   Custo R$ 0. Mistura sugerida: 30% real / 70% sintético, com o real oversampled.
5. Baselines no gold: (a) tesseract sobre os recortes de linha, (b) o próprio modelo base zero-shot
   nos recortes, (c) referência g2b 98,85% / consenso 99,06%.

**Treino (G4.3):** TRL `SFTTrainer` + PEFT LoRA, bf16, encoder congelado, 3–5 épocas sobre a
mistura, lr 1e-4 (LoRA), batch efetivo 16, avaliação por época no dev split com a métrica de
célula (exact match numérico) e com `validate_sheet` sobre as tabelas remontadas. Seleção do
checkpoint pelo dev, não pelo gold. Hash do manifesto verificado no launch contra a guarda.

**Avaliação (G4.4):** as 9 páginas gold pelo pipeline completo (recortes → modelo → `assemble_sheet`
→ `restore_thousands` → `qc.flag_violations`) e `metrics.score`; o controlador recomputa
independentemente. Régua: ≥ ~95% com o QC existente = SHIP; abaixo mas acima do tesseract e com
erros diagnosticáveis = 1 retreino dirigido; senão resultado negativo honesto.

## 6. Licença dos rótulos: pendência que o owner tem de decidir

A memória do lab manda checar a licença de quem GERA os rótulos antes de treinar (lição MMS_FA).
Checado hoje:

- **Gemini API Additional Terms (vigência 2026-03-23)**, verbatim: *"You may not use the Services
  to develop models that compete with the Services (e.g., Gemini API or Google AI Studio)."* Sobre
  o conteúdo gerado: *"Google won't claim ownership over that content."* Os rótulos são nossos; a
  única barreira é "modelos que competem com os Serviços". Um leitor de 0,9B para tabelas
  meteorológicas do século XIX é difícil de enquadrar como concorrente da Gemini API, mas a cláusula
  é vaga e quem julga é o Google. **Risco residual, não permissão limpa.**
- Anthropic Commercial Terms (D.4) têm a mesma estrutura ("train competing AI models").
- **Gemma Terms (2026-04-01)**: modelo treinado em saídas do Gemma vira "Model Derivative" preso aos
  termos Gemma. Não usar Gemma como rotulador.
- **Apache-2.0 (Qwen3-VL/3.5, PaddleOCR-VL) e MIT (DeepSeek-OCR)**: nenhuma cláusula sobre saídas.
  Treinar em rótulos deles é irrestrito.

Opções:
- **A. Seguir com os rótulos Gemini** (o dataset já pago, 99%), passando-os pela revisão humana dos
  flags (Task 2c do G3) e declarando a proveniência no model card. Minha posição: risco baixo e é o
  caminho que preserva a qualidade de rótulo. Recomendo A.
- **B. Rerotular com um modelo Apache** (Qwen3-VL-8B ou o próprio PaddleOCR-VL zero-shot via HF
  Inference ou Jobs em `l4x1`), estimativa < US$ 5 para ~30 páginas, e revisar os flags à mão. Zera a
  dúvida de ToS, mas a acurácia desses rotuladores nessa tipografia é desconhecida e o desenho
  g2b (schema, âncora, header) teria de ser reimplementado para eles. Mais trabalho, rótulo pior.
- Em qualquer caso, o **gold humano** e os **sintéticos** são limpos.

## 7. Compute e custo

**Preços HF Jobs (verificado hoje, cobrança por minuto, exige crédito pré-pago, sem PRO):**

| flavor | GPU / VRAM | US$/h |
|---|---|---|
| `t4-small` | T4 16 GB | 0,40 |
| `l4x1` | L4 24 GB | 0,80 |
| `a10g-small` | A10G 24 GB | 1,00 |
| `l40sx1` | L40S 48 GB | 1,80 |
| `a100-large` | A100 80 GB | 2,50 |

Timeout padrão de job 30 min: passar `--timeout` explícito. Não há mais H100 em Jobs.

**Estimativas de treino (estimativa; o smoke run calibra):**

| Cenário | Onde | Tempo | Custo |
|---|---|---|---|
| Smoke LoRA, 300 linhas reais, 1 época | M4 (Paddle 0,9B) | ~1 h | R$ 0 |
| LoRA linha, 900 reais + 30k sintéticas, 3 épocas, Paddle 0,9B | `l4x1` | ~1–2 h | ~US$ 1–2 |
| Idem, Qwen3.5-2B | `l4x1` / `a100-large` | ~2–4 h / ~1 h | ~US$ 3 |
| Página inteira (experimento), 29 páginas + sintético, 5 épocas, 2B | `a100-large` | ~1–2 h | ~US$ 3–5 |
| Retreino dirigido (1 permitido pela régua) | | | ~US$ 5 |
| **Total previsto G4.3, com 2 bases + 1 retreino** | | | **~US$ 15–25** |
| Top-up de rótulos Gemini (só se a Revista não terminar) | consenso n=3 ≈ US$ 0,05/tabela | | < US$ 2 |
| Rerotulagem Apache (opção B da seção 6) | | | < US$ 5 |
| Avaliação, inferência, empacotamento, demo de escala | M4 | | R$ 0 |

Compute total **< US$ 40** contra o teto aprovado de US$ 50–150. Cada launch pago continua com
cap declarado antes e confirmação por gasto.

**Viabilidade no próprio M4 (16 GB):** inferência de qualquer candidato ≤2B em bf16 cabe. Treino
LoRA do Paddle 0,9B em recortes de linha cabe (pesos ~2 GB + ativações pequenas). Treino do
Qwen3.5-2B em recorte de linha é limítrofe; em página inteira não cabe. Números medidos do smoke
test zero-shot na seção 8.

## 8. Smoke test local (medido no M4, 2026-09-02)

Qwen3-VL-2B-Instruct (2,1B, bf16, MPS, `transformers.generate` sem otimização), página gold 22
(Dez 1885), zero-shot, sem fine-tune. Modelo usado só por já estar disponível; o Qwen3.5-2B e o
Paddle 0,9B são os candidatos reais.

| Medida | Página inteira (redimensionada a 75%) | Recorte de linha (`crop_row_bands`, 4980×178) |
|---|---|---|
| Tokens de entrada | 2.392 | 994 |
| Geração | 3.000 tokens em 201 s (14,9 tok/s), saída truncada em 25 de 31 linhas | 69–120 tokens em 6–9 s por linha |
| Memória | pico 4,1 GB MPS / 5,7 GB driver | 4,7 GB driver |
| Load do modelo | 62 s | — |
| Acurácia vs gold | **89/350 = 25,4%** de células (com reconstrução do barômetro) | linha 1: **14/14**; linha 16: **14/14** (leu "Gottas" onde o gold tem vazio+flag); linha 2: recorte pegou duas linhas e o modelo repetiu valores da linha 1 |

Leituras:
- **Página inteira zero-shot é o piso: 25%.** Confirma que fine-tune é obrigatório nesse caminho e
  que 3.000 tokens de saída a 15 tok/s (200 s/página) é lento demais no M4 sem quantização.
- **Recorte de linha zero-shot já lê ~perfeito** quando o recorte contém uma linha só. É a
  evidência mais forte a favor da seção 3: a dificuldade está na estrutura, não nos glifos, e a
  estrutura a geometria já resolve. O fine-tune por linha parte de um piso alto.
- **O erro da linha 2 é do recorte, não do modelo** (`band_height_factor=1.8` inclui a vizinha).
  Task G4.0 tem de apertar a banda e validar a geometria por página. Também explica a
  precisão 7/15 do zoom-flagger do G3.
- Throughput zero-shot por linha: ~7 s × 31 ≈ 4 min/página no M4 neste setup. Com Paddle 0,9B e
  MLX/GGUF a meta é < 1 min/página; a demo de escala do G4.5 mede isso.
- Memória: 16 GB são suficientes para inferência; para treino LoRA por linha do 0,9B também.

## 8b. Zero-shot nos recortes de linha do gold (medido 2026-09-03) — DECISÃO REVISTA

40 linhas gold amostradas (seed 0), pontuação estrita por ordem de tokens (14 tokens ou a linha
inteira conta errada), `scripts/g4_zero_shot.py`, `bench/g4/zero_shot-*.json`.

| Modelo | Acurácia de célula | Linhas com 14 tokens | s/linha no M4 | Observação |
|---|---|---|---|---|
| tesseract `--psm 7` | 1,8% (183 linhas) | 22/183 | 0,2 | não lê a tipografia |
| PaddleOCR-VL-1.6, prompt `OCR:` | 22,5% | 19/40 | **36,1** | lê os dígitos mas emenda tudo sem separador ("758.3460.7256.24…"); muito lento no MPS |
| Qwen3-VL-2B-Instruct | 31,8% | 29/40 | 4,7 | (baseline anterior) |
| **Qwen3.5-2B** | **31,8%** | 31/40 | **7,1** | leituras quase todas certas; erra alinhamento (null, eco do dia, "……") |

**Decisão: Qwen3.5-2B é a base do smoke e do treino**, não o Paddle. O Paddle tinha o melhor
TEDS publicado, mas no nosso caso (uma linha por vez, MPS) é 5× mais lento e sai sem
estrutura. O Qwen3.5-2B segue instrução, produz os separadores e lê os glifos bem; o que falta
é exatamente o que o fine-tune ensina. A licença dos rótulos foi decidida pelo owner
(2026-09-03): **opção A**, seguir com os rótulos Gemini e declarar proveniência.

## 9. Riscos e o que já está decidido contra eles

- **Estações secundárias (Corumbá, 2 leituras/dia, ~60 linhas)** quebram o schema de 31 linhas:
  ficam FORA do treino v1 e do gold. Decisão a registrar no plano-pai.
- **Sintético infiel** (fontes erradas ensinam o modelo errado): validar a mistura no dev split
  real; se sintético não ajudar o dev, cortar.
- **Recorte desalinhado**: geometria checada por página; página sem 31 bandas nítidas sai do
  treino; margem vertical maior que no zoom do G3.
- **Modelo lê 95%, não 99%**: aceitável pelo plano com o QC de flags + revisão humana; o número
  vai declarado.
- **Rate limit / API fora**: irrelevante depois do G4.0, é o ponto todo.

## 10. Ordem de execução e paradas

1. G4.0 (R$ 0, agora ou quando a Revista terminar): dataset por linha + guarda + baselines +
   renderizador sintético. STOP: tamanho do conjunto, baselines.
2. G4.1: confirmar Paddle-primeiro + decisão de licença (A ou B). STOP.
3. G4.2 (R$ 0): `local_model.extract` com Paddle zero-shot, medir piso no gold. STOP.
4. G4.3: smoke LoRA no M4; depois `l4x1` com cap US$ 10 declarado. STOP com custo e curvas.
5. G4.4: gold, recomputo independente, relatório em português. STOP: ship / retreino / kill.
6. G4.5: GGUF ou MLX, 100+ páginas locais, páginas/hora, custo por página US$ 0.

Fontes: ver os URLs nas notas de pesquisa desta sessão; principais:
huggingface.co/docs/hub/jobs-pricing · ai.google.dev/gemini-api/terms · ai.google.dev/gemma/terms ·
huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 · huggingface.co/Qwen/Qwen3.5-2B ·
huggingface.co/ibm-granite/granite-docling-258M · huggingface.co/docs/trl/main/en/sft_trainer ·
github.com/Blaizzy/mlx-vlm
