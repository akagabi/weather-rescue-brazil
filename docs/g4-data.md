# G4.0 — Conjunto de treino por linha, guarda de vazamento e baselines

Data: 2026-09-03. Custo: R$ 0 (tudo local). Branch `g4-offline-model`.
Contexto e decisões de desenho: `docs/g4-model-choice.md` (seções 3 e 5).

## 1. O que foi construído

| Peça | Onde | O que faz |
|---|---|---|
| Localizador de linhas | `src/wrb/rows.py` | Acha as N linhas-dia de uma página da Revista: Otsu numa janela estreita (coluna do dia + 1º barômetro), máscara de réguas verticais, deskew, passo por autocorrelação (vários candidatos), picos do perfil suavizado, cadeia de passo uniforme que não cruza régua horizontal, remoção das linhas "Déc."/"Mez" (isoladas) e da linha de unidades (sem tinta na coluna do dia). Recusa a página se não fechar em N. |
| Montagem do dataset | `src/wrb/dataset.py` | 1 exemplo = 1 recorte de linha (altura = 1 passo, largura da tabela, 2×) + as 14 células daquele dia da transcrição g2b+consenso. Manifesto com sha256 por imagem. |
| Guarda de vazamento | `dataset.assert_no_gold_leakage` | Falha se qualquer exemplo de treino vier de página gold (id), estiver marcado `is_gold`, ou tiver sha256 igual a um recorte gold. Roda ao fim do build e deve rodar no launch do treino (`manifest_hash`). |
| Oráculo do número do dia | `scripts/g4_build_dataset.py` | Qwen3-VL-2B local zero-shot lê o número do dia de um recorte. Usado só para (a) escolher a janela certa quando a cadeia sai 1–3 linhas longa demais e (b) verificar 3 linhas amostradas por página aceita. Nunca gera rótulo. |
| Baselines | `scripts/g4_baselines.py` → `bench/g4/baselines.json` | tesseract e VLM zero-shot nos recortes gold (seção 4). |
| Testes | `tests/test_rows.py` (página sintética), `tests/test_dataset.py` | 155 testes verdes no total. |

## 2. Resultado da montagem (medido)

| | Treino (não-gold) | Gold (só avaliação) |
|---|---|---|
| Páginas aceitas | 22 de 28 (18 direto + 4 via oráculo) | 6 de 9 (3 direto + 3 via oráculo) |
| Linhas | **668** | 183 |
| Células não vazias | **7.968** | 2.425 (de 3.822 no gold completo) |
| Por volume (linhas) | 15: 334 · 16: 273 · 14: 61 | 14 |
| Verificação do oráculo | 84 leituras de número do dia em páginas aceitas, **0 divergências** | idem |
| Guarda de vazamento | PASS | — |
| Manifesto | `data/g4/train_manifest.json` (hash `d8fe4e09f4da`) | `data/g4/gold_manifest.json` |

Células por coluna no treino: pressão/temperatura/vapor/umidade ~660 cada; nebulosidade 628;
evaporação à sombra 533; ozônio 602; precipitação 227; evaporação ao sol 121 (só existe no vol. 14).
Flags: `wind_dir` (texto) em 663 linhas; flags de célula (vapor, precip, tmax…) em 13.

**Correção de rota vs. o plano:** a geometria do G3 (`crop_row_bands`, passo uniforme entre duas
réguas, banda 1,8×) não serve para treino: nas páginas dos vols. 15/16 as linhas "Déc." quebram
o passo uniforme, e a banda 1,8× pega a linha vizinha (o smoke test viu o modelo copiar a
vizinha). O localizador novo lê as linhas de fato da página. Inspeção visual de 4 páginas × 9
linhas (dias 1, 2, 3, 10, 11, 20, 21, N-1, N): todas alinhadas, uma linha por recorte.

## 3. Páginas recusadas (9) — vão para revisão humana, não para o treino

| Página | Período | Motivo |
|---|---|---|
| 14/22 (gold) | 1885-12 | cadeia com 38 linhas: réguas do vol. 14 muito claras, notas de rodapé (passo parecido) entram na cadeia |
| 14/41 (gold) | 1886-01 | 32 linhas; oráculo não achou janela começando no dia 1 |
| 14/57 (gold) | 1886-02 | 29 linhas (28 esperadas); idem |
| 14/158 | 1886-08 | cadeia curta (27 de 31) |
| 15/44 | 1889-01 | 32 linhas; oráculo não achou janela |
| 15/108 | 1889-05 | 32 linhas; idem |
| 16/22 | 1889-12 | 36 linhas (dia 2 impresso como pontos; Déc. não isolada) |
| 16/38 | 1890-01 | 32 linhas; oráculo não achou janela |
| 16/107 | 1890-06 | cadeia curta (24 de 30) |

Implicação honesta: **a avaliação por linha hoje cobre 6 das 9 páginas gold (2.425 de 3.822
células)**. Antes do G4.4 isso tem de virar 9/9. Duas saídas, ambas R$ 0: (a) mais uma rodada no
localizador focada no vol. 14 (réguas claras); (b) caixas de linha marcadas à mão para as 3 páginas
gold recusadas — legítimo porque o gold é só avaliação e a geometria não é o que se avalia.
Recomendo (b) para destravar e (a) só se as páginas de treino recusadas fizerem falta.

## 4. Baselines no gold (por linha, 183 linhas / 2.425 células)

Método: tokens numéricos em ordem de leitura; a linha só é pontuada célula a célula quando saem
exatamente 14 tokens (token i → coluna i); qualquer outra contagem = erro estrutural, 14 células
erradas. Barômetro sem o "7" restaurado com `restore_thousands`, como no g2b. Números em
`bench/g4/baselines.json`.

| Leitor | Linhas | Células | Linhas com 14 tokens | Acurácia de célula |
|---|---|---|---|---|
| tesseract `--psm 7` (OCR genérico) | 183 | 2.562 | 22 | **1,8%** |
| Qwen3-VL-2B zero-shot (sem fine-tune), amostra | 40 | 560 | 29 | **31,8%** |
| Referência: g2b API single-shot / consenso (página inteira, 9 páginas) | — | 3.822 | — | 98,85% / 99,06% |

Leitura honesta dos dois pisos: o tesseract simplesmente não lê esta tipografia. O VLM zero-shot
lê os glifos bem (o smoke test viu 14/14 em linhas limpas) mas **não produz as 14 posições**: em
11 de 40 linhas saíram menos/mais tokens (células vazias viram "null" ou somem, o dia ecoa,
"Gottas" vira nada), e a pontuação por ordem derruba a linha inteira. Alinhamento de coluna é
exatamente o que o fine-tune ensina; por isso o número que o modelo treinado tem de bater é
31,8% (piso) e o que tem de aproximar é 99% (teto do método).

## 5. Distribuição e o que falta para treinar

- 668 linhas reais é o piso de dados real. A augmentação sintética (seção 5 do
  `g4-model-choice.md`) continua obrigatória; ainda não foi construída (próximo passo R$ 0).
- O split dev deve separar 2 páginas inteiras do treino (não linhas soltas). Sugestão: 15/60
  (fev, 28 dias) e 16/159.
- Estações: as páginas dos vols. 15/16 são do **Observatório de Santa-Cruz** (título impresso na
  página), mas o `pred.station` do bench diz "Rio de Janeiro - Observatorio Astronomico" — é
  metadado do script de run, não leitura da página. Não afeta o treino por linha; **afeta o
  dataset publicado (G3 Task 3)** e precisa ser corrigido lá.
- Corumbá (2 leituras/dia, 62 linhas, página 16/72) já estava fora do bench; fora do treino v1.

## 6. Reprodução

```
python scripts/g4_build_dataset.py --verify 3     # ~2 min no M4 (oráculo local)
python scripts/g4_baselines.py --vlm-rows 40      # tesseract em 183 linhas + VLM zero-shot em 40
python -m pytest -q
```

---

## 7. Atualização 2026-09-04 (madrugada): smokes 1–2, geometria corrigida, rebuild por oráculo

**Treinos no M4 (Qwen3.5-2B, LoRA r=16 só no LM, R$ 0):**

| Run | Dados | Dev (59 linhas, vols. 15/16) | Gold (linhas, vol. 14) | Notas |
|---|---|---|---|---|
| smoke1 | 609 linhas reais, 1 época | 98,4% | **80,4%** (183 linhas, 6 páginas) | 364/501 erros nas 3 colunas da direita: modelo aprendeu o layout dos vols. 15/16 (sem "Sol") |
| smoke2 | idem + hint de layout por volume + vol. 14 ×4, 2 épocas | 99,3% | **84,8%** (183 linhas) | 183/183 linhas no formato; por página 63–98% |

**Diagnóstico do smoke2 (bench/g4/smoke2-epoch2.json):** três páginas gold a 96–98% (75, 109, 212)
e três a 63–80% (90, 142, 179). Nos recortes das páginas ruins, o lado direito da linha estava
meia linha deslocado: o deskew grosseiro (janela estreita à esquerda, passo 0,1°) não vê a
deriva 1200 px à direita, e o modelo lia as células da vizinha. **Erro de geometria, não de leitura.**

**Correções (commits d26d2e1, f5fb886):**
1. `rows.refine_skew`: ângulo fino pela correlação dos perfis de linha entre a janela esquerda
   (coluna do dia) e uma janela nas colunas vapor/umidade. Alinhamento verificado visualmente
   borda a borda nas páginas 22, 75, 90, 142, 179.
2. Localização **dirigida pelo oráculo em toda página**: o localizador só propõe candidatos; o
   Qwen3-VL-2B lê o número do dia impresso em cada candidato e a linha d vai para o candidato que
   lê d (monotonicidade + espaçamento checados; dias sem leitura interpolados dos vizinhos). A
   verificação amostral anterior tinha pego páginas "ok" deslocadas em 2–3 linhas (14/212, 15/72,
   15/141) — o que teria envenenado rótulos e o gold.

**Rebuild (commit efb86ed):**

| | Treino | Gold |
|---|---|---|
| Páginas | 25 de 28 (recusadas 14/141, 16/38, 16/174: poucas leituras diretas) | **9 de 9** |
| Linhas / células | 762 / 9.104 | 273 / 3.622 (de 3.822) |
| Dias lidos diretamente pelo oráculo | 899 de 1.035 (87%); resto interpolado | |
| Linhas vol. 14 no treino | 62 (páginas 158 e 195) | |

**smoke3 (rodando):** dados rebuildados, vol. 14 ×8, augmentação fotométrica/geométrica
on-the-fly, 3 épocas, checkpoint a cada 20 passos, gold 9/9 ao fim.
