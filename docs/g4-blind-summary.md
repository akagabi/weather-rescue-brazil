# G4 — Evidência cega acumulada: quatro layouts, duas publicações

Data: 2026-09-07. Modelo: Qwen3.5-2B + LoRA (`runs/g4/gen3/epoch2`), **treinado em dois layouts,
400 linhas, no M4, R$ 0**. Nenhum dos layouts abaixo estava no treino.

| # | layout | colunas | linhas testadas | como foi verificado | resultado |
|---|---|---|---|---|---|
| 1 | Revista, Rio 1886 | 16 | 30 | gold humano triplamente verificado | 90,7% |
| 2 | Porto do Maranhão 1886 | 12 | 24 (página inteira) | lido à mão **e** o total mensal de chuva impresso (150,90 mm) fecha | **95,8% numérico** |
| 3 | Rio 1883, tensão do vapor (francês) | 9 | 14 | checksum por linha: Moyenne = média das 7 leituras | **98,4%** |
| 4 | Rio 1883, termômetros | 13 | 28 (página inteira) | **a própria aritmética da página**: Oscil = Max − Min, 2× por linha | **96,4%** |

Duas publicações distintas (Revista do Observatório; Annaes de 1883), duas línguas, contagens de
coluna de 9 a 16, cabeçalhos aninhados, colunas de texto livre e valores textuais (`Inap.`)
dentro de colunas numéricas.

## O que cada teste acrescenta

- **#2** é o mais forte em verdade: 264/264 números certos, e a coluna de chuva **lida pelo modelo**
  soma exatamente o total que o tipógrafo imprimiu em 1886 — o documento validando o modelo.
- **#3** é a primeira publicação diferente, e foi ele que revelou a contaminação de convenção
  (`docs/g4-print-fidelity.md`) — invisível dentro do corpus de origem.
- **#4** é o primeiro teste **sem nenhum rótulo humano**: o perfil declara a aritmética
  (`Profile.checks`) e a página se corrige sozinha. A única linha que falhou apontou um dígito:
  o modelo leu `34.1`, a página imprime `33.1`, e 33,1 − 23,9 = 9,2 fecha.

## Por que isso sustenta a tese do framework

Adaptar a uma publicação nova custa **dezenas de linhas** (`docs/g4-learning-curve.md`: 20 linhas
já dão 92–97%), e **validar não custa nada** onde a tabela declara a própria aritmética. Os dois
juntos são o que torna plausível varrer um arquivo inteiro sem uma equipe de transcritores.

## Limite honesto

Tudo é impresso, brasileiro, das décadas de 1880, do mesmo acervo digitalizado (DocVirt/ON). Uma
varredura de 56 páginas nas outras 12 obras do acervo não achou mais tabelas — são texto corrido.
Um terceiro corpus, de outro arquivo e de preferência não brasileiro, é o próximo passo para a
afirmação valer além disso.

## Terceiro corpus: Radcliffe Observatory, Oxford (arquivo e país diferentes)

Buscado e baixado do Internet Archive (domínio público, educado: sequencial, ≥2 s, UA do projeto).
`astronomicaland03obsegoog` p.138, Tabela I: **médias mensais do barômetro, 1855–1879**.

Nada aqui se parece com o treino: **Inglaterra, inglês, barômetro em POLEGADAS**, digitalização do
Google (não DocVirt), e a **semântica da tabela é invertida — linhas são ANOS, colunas são MESES**.
Ponto decimal elevado, com a parte inteira (29) elidida e impressa só quando muda (`30·108`,
`29·721`). Seis linhas lidas à mão, **todas verificadas pelo checksum da própria página** (a média
anual impressa = média dos 12 meses).

| | resultado |
|---|---|
| Células corretas (alinhamento corrigido) | **62/70 = 88,6%** |
| Só as colunas de dados (excluindo a do ano) | **~94%** |

**Erros, todos diagnosticáveis:** 4 dos 8 são a coluna do ANO lida como `18` em vez de `1856` — o
recorte corta o ano na borda esquerda (`table_x_frac` calibrado para tabelas brasileiras), ou seja
geometria, não leitura. Restam uma troca de duas colunas e um `29·968` lido sem a parte inteira.

### Duas limitações reais que este corpus expôs

1. **Resolução mínima.** O scan tem 898 px de largura (o máximo que o Google produziu) para 14
   colunas; o localizador achava 4 linhas de 25. Corrigido de forma geral: `wrb.rows` agora detecta
   passo abaixo de `MIN_PITCH_PX` e refaz a localização com a página em 2×, devolvendo as caixas na
   escala original. Passou a achar 25/25. Nenhuma página brasileira mudou; 171 testes verdes.
2. **A janela de sondagem é calibrada para a coluna do dia** brasileira. Aqui a coluna do ano fica
   noutro lugar, e foi preciso passar `probe_x_frac` explicitamente. Isso deveria ser um campo do
   perfil, não um argumento — pendência anotada.

**Leitura honesta:** o primeiro teste deu **0/56**, e valeu mais do que teria valido um acerto: o
zero era localização (o modelo lia linhas reais, só que não as que eu havia rotulado), e apontou um
limite de resolução que nenhum corpus brasileiro teria revelado.
