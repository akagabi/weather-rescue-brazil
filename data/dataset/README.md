# Weather Rescue Brazil — dataset v0.1 (rascunho, não publicado)

Transcrição automática de tabelas meteorológicas impressas do século XIX, lida **offline** por um
modelo aberto de 2B rodando num laptop. Gerado por `scripts/g4_produce.py` com o adaptador
`runs/g4/gen3/epoch2`.

## Conteúdo

| | |
|---|---|
| Linhas | 1.194 (954 utilizáveis, 79,9%) |
| Valores nas linhas utilizáveis | **13.441** |
| Páginas | 39 |
| Publicações | 4 layouts / 2 obras |
| Período | 1885-12 a 1890-11 |
| **Nunca digitalizado antes** | **85 linhas** — Porto do Maranhão (Fev 1886) e Corumbá (Dez 1889), ambos localizados nesta sessão |

## Formato

Uma linha JSON por linha de tabela:

- `values_as_printed` — **o que está impresso**, sem correção silenciosa;
- `values` — o mesmo, com as convenções da publicação desfeitas em código (barômetro com os
  milhares repostos), determinístico e reversível;
- `markers` — palavras que a página imprime no lugar de um número (`Gottas`, `Inap.`), preservadas;
- `verdict` — `checks_pass` (a aritmética da própria página fecha) / `qc_clean` (tudo dentro das
  faixas físicas) / `flagged` (motivo registrado em `problems`, `range_violations`, `check_failures`);
- `padded_trailing` — a leitura veio com uma célula a menos e assumiu-se que a ausente é a última.
  **É uma suposição, marcada e não escondida**;
- procedência completa: `archive`, `item`, `page`, `period`, `row`, `profile`, `source`.

Consumidor que quiser só o subconjunto garantido: filtre `verdict != "flagged"` e, se quiser ser
estrito, `padded_trailing == false`.

## Qualidade

Medida contra o gold humano e testes cegos (`docs/g4-blind-summary.md`): 88–99% de acerto por
célula conforme o layout, com 100% dos números numa página inteira do Maranhão verificada à mão.
Nesta produção, **240 linhas ficaram sinalizadas em vez de entrar erradas** — o comportamento
desejado.

## Limitações conhecidas (honestas)

- **82 linhas do Rio 1886** trazem uma célula `null` a mais entre nebulosidade e chuva: o modelo
  percebe ali uma divisória que o perfil não declara. É consistente, então é uma questão de perfil,
  não de leitura. Elas estão sinalizadas.
- **24 linhas** produziram saída degenerada (sequências como `1 | 2 | 3 …`) em linhas de cabeçalho
  ou de resumo mensal; sinalizadas.
- Nada aqui passou por revisão humana linha a linha. O gold congelado (9 páginas) **não** faz parte
  deste arquivo — é conjunto de avaliação.
- Ainda não exportado para SEF/C3S; é o passo seguinte antes de qualquer publicação.

## Proveniência e direitos

Imagens: Biblioteca Digital de Obras Raras do Observatório Nacional, via DocVirt (sem CAPTCHA,
acesso público). Obras de 1886–1890, domínio público no Brasil (Lei 9.610). A atribuição do acervo
acompanha cada página baixada em `data/raw/docvirt/*/*.json`.
