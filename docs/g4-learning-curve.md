# G4.10 — Curva de aprendizado: quantas linhas rotuladas custa uma publicação nova?

Data: 2026-09-07. `scripts/g4_learning_curve.sh`, `bench/g4/blind-*-curve*.json`.

A afirmação central do framework era **"~40 linhas por publicação"**. Era suposição. Isto mede.

## Desenho

Receita idêntica, épocas idênticas, conjuntos de teste idênticos. **A única variável é o número de
linhas DISTINTAS rotuladas por layout** (Santa-Cruz e Corumbá, sempre equilibradas — ver
`docs/g4-print-fidelity.md` sobre por que distintas e não repetidas). Cada ponto é testado às
cegas em **duas publicações que o modelo nunca viu**.

## Resultado

| linhas distintas por layout | Maranhão (12 col.) | Maranhão só numéricas | Rio 1883 francês (9 col.) |
|---|---|---|---|
| 10 | 86,5% | 87,1% | 77,8% |
| 20 | 92,0% | 91,7% | 96,8% |
| **40** | **95,1%** | **95,8%** | **98,4%** |

- **Monotônica nos dois testes cegos**, sem platô até 40. Mais linhas provavelmente ainda ajudam.
- **20 linhas já entregam 92–97%**, o que muda o custo prático: meia hora de trabalho, não uma
  tarde, para uma publicação nova ficar utilizável com revisão por QC.
- O salto de 10→20 é o maior no teste francês (77,8% → 96,8%): abaixo de ~20 o modelo ainda não
  tem exemplos distintos suficientes de cada convenção tipográfica.

## O que isso significa para o framework

O custo de adaptação é **dezenas de linhas, não milhares**, e é medido, não estimado. Combinado com
o resto do sistema — perfil em JSON, localizador de linhas agnóstico, workbench, validação por
checksum — o orçamento de uma publicação nova é:

| passo | custo |
|---|---|
| escrever o perfil (colunas impressas) | ~2 min na interface |
| rotular 20–40 linhas | 20–40 min |
| treinar (M4, R$ 0) | ~45 min desatendido |
| validar | grátis onde a tabela traz aritmética própria |

## Ressalva honesta

A curva é medida em **duas** publicações cegas, ambas brasileiras, impressas, da década de 1880, do
mesmo acervo digitalizado. A forma da curva deve valer além disso; os valores absolutos, não
necessariamente.
