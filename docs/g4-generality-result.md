# G4.7 — Generalização: o modelo passou a ler o número de colunas na imagem

Data: 2026-09-07. Custo: R$ 0 (M4). Arquivos: `scripts/g4_build_generality_set.py`,
`scripts/g4_test_generality.py`, `bench/g4/generality-gen1.json`,
`data/g4/generality_manifest.json`.

## 1. A pergunta

Em `docs/g4-generalisation.md` o modelo falhou num layout inédito por um motivo exato: **emitia
sempre 15 células**, porque 15 era a contagem do layout Santa-Cruz, que era 91% do treino. Ele
aprendeu o número, não aprendeu a olhar.

Hipótese: o problema é **desequilíbrio**, não falta de variedade — o smoke5 já tinha visto 15 e 16
células e mesmo assim decorou 15.

## 2. O desenho (honesto)

| | |
|---|---|
| Treino | 200 linhas Santa-Cruz (**15** células impressas) + 40 linhas Corumbá lidas à mão ×5 (**16** células) = 400 linhas, **50/50** |
| Fora do treino | **Rio (docId 14) inteiro** — verificado por asserção no script de montagem; os docs no manifesto são só 15 e 16 |
| Teste | 30 linhas do gold congelado do Rio (16 células impressas), **verificado por humanos**, layout que o modelo nunca viu |
| Modelo | Qwen3.5-2B + LoRA r=16, alvo livre de esquema, 2 épocas (a 3ª foi abortada: máquina na bateria, dev já estável) |

Rio é o teste certo justamente por ser o único layout com verdade humana **e** o único que o
modelo não viu.

## 3. Resultado

| Métrica | smoke5 (desequilibrado) | **gen1 (equilibrado)** |
|---|---|---|
| Células emitidas num layout inédito | sempre 15 | **16 em 27 de 30 linhas (90%)** |
| Acurácia de célula vs gold humano | ~0 posicional | **96,19% (404/420)** |

Recomputado independentemente a partir das predições salvas contra `gold_manifest.json`: 404/420.

Para comparar: o modelo **treinado no Rio** faz 99,08% nessas páginas. Este, **sem nunca ter visto
o Rio**, faz 96,19%.

## 4. O que isso significa

**O equilíbrio era a correção.** Com 15 e 16 células em partes iguais, o modelo parou de chutar a
contagem e passou a lê-la na imagem. Não foi arquitetura nova, nem truque de prompt, nem mais
parâmetros: foi composição do conjunto de treino.

Consequência prática para o arquivo brasileiro: **cada publicação nova entra com ~40 linhas
rotuladas à mão** (uma hora de trabalho no workbench) e o modelo compartilhado melhora para a
próxima. Não é um modelo por publicação; é um leitor de tabelas.

## 5. Ressalvas

- **N pequeno**: 30 linhas de teste, 2 épocas, um único layout inédito. É sinal forte, não prova.
  O próximo passo é um quarto layout, de outra publicação, como teste realmente cego.
- As 3 linhas com 15 células mostram que a contagem ainda falha às vezes; o QC do perfil pega isso
  (`N células, esperava 16`) e manda para revisão em vez de gravar errado.
- Os rótulos de Corumbá são meus, lidos à mão de recortes 3×, não triplamente verificados como o
  gold. Erro meu vira erro de treino.
- A 3ª época não rodou. Com ela o número provavelmente sobe um pouco.
