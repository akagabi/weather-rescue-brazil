# Detecção automática de colunas a partir do cabeçalho (teste 2026-09-06)

Pergunta: dá para outro modelo ler o cabeçalho impresso e gerar o perfil, em vez de a pessoa
digitar os rótulos?

Modelo: Qwen3-VL-2B-Instruct (MLX bf16, local, R$ 0). Recorte = a faixa acima da primeira linha de
dados, achada pela geometria. Um prompt, três layouts.

| Página | Colunas impressas | O que o modelo listou | Veredito |
|---|---|---|---|
| Rio (14/22) | 16 | 8 grupos, com o conteúdo CERTO: `BAROMETRO A 0° — Medias diurnas, Maximas, Minimas`, `EVAPORAÇÃO — Sol, Sombra` | quase: leu certo, não expandiu os grupos em subcolunas |
| Santa-Cruz (15/60) | 15 | 16 linhas, rótulos quase todos certos, mas prefixou tudo com `DATA —` e trocou a ordem das duas últimas | parcial |
| Corumbá (16/72) | 16 | tudo colapsado em UMA linha | falhou |

**Conclusão.** Mesma fraqueza das linhas: o modelo pequeno **lê o texto** do cabeçalho bem e
**não produz estrutura** de forma confiável. Cabeçalhos agrupados (um título cobrindo três
subcolunas) são o ponto exato onde ele quebra.

**Implicação de arquitetura (importante).** Nomear colunas é uma tarefa **uma vez por
publicação**, não uma vez por página — talvez uma chamada por acervo inteiro. Portanto é
exatamente onde um modelo grande / API paga é a ferramenta certa, ao custo de frações de centavo,
enquanto o modelo local faz as milhões de leituras por linha, onde o custo importa. Caro onde é
raro, grátis onde é quente.

**Próximo passo natural (não feito):** híbrido — a geometria conta as colunas pelas réguas
verticais (contagem confiável) e o modelo só as nomeia (texto, que ele acerta). Depende da
detecção de colunas ficar confiável; a primeira tentativa (`wrb.synth.column_gaps`) fechou a
contagem certa em 1 de 5 páginas.
