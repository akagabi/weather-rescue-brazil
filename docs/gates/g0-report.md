# Gate G0 — Relatório final

Data: 2026-08-31. Gasto até aqui: **R$0,00 / US$0,00** — nenhuma chamada de
API paga foi feita em nenhuma tarefa deste gate; `data/ledger.json` (o
arquivo que registraria qualquer gasto) **não existe** no repositório,
confirmando o zero gasto por ausência de registro, não por omissão de
checagem.

## 1. Veredito de acesso

`docs/access.md` (Task 2): **BULK FETCH: PERMITTED WITH CARE** para
`memoria.bn.gov.br` (Hemeroteca Digital Brasileira, BN) e `docvirt.com`
(Observatório Nacional). Nenhum dos dois hosts declara restrição via
`robots.txt` (ambos 404 — arquivo inexistente). A BN permite explicitamente
reprodução de material em domínio público, exigindo apenas atribuição
("Acervo Fundação Biblioteca Nacional") e respeito à janela de 70 anos da
Lei 9.610 (mais precisa que o atalho "pré-1955" do spec original, mas
"pré-1955" continua um subconjunto seguro dela). Nada no termo da BN proíbe
automação — o fluxo descrito é manual, mas não há vedação escrita.

**Achado de TLS** (`docs/access.md` §3, aprofundado em
`docs/docreader-endpoints.md` §5): `memoria.bn.gov.br` envia apenas o
certificado-folha (`CN=*.bn.gov.br`, emissor "Certum DV TLS G2 R39 CA") e
omite o intermediário — clientes estritos (`httpx`/`certifi`, OpenSSL)
recusam a cadeia; browsers funcionam só porque buscam o intermediário via
AIA ou já o têm em cache. Não é falha do ToS, é housekeeping de servidor;
já corrigido e commitado (`src/wrb/certs/bn-intermediate.pem`, usado
automaticamente por `wrb.fetch_docreader._bn_ssl_context()`). O mesmo tipo
de lacuna, dois certificados mais funda, apareceu depois em
`www.estacao.iag.usp.br` e foi corrigida da mesma forma
(`src/wrb/certs/iagusp-intermediate.pem`).

**Desenvolvimento posterior ao veredito** (`docs/docreader-endpoints.md`
§3, Task 4): em 03/10/2025 a BN adicionou um **CAPTCHA obrigatório por
documento** ao visualizador DocReader (não ao host em geral). Nenhuma
imagem é servida antes de resolver o CAPTCHA; é por-documento, não
por-sessão (resolver para um documento não libera outro). Isso não
invalida o veredito "PERMITTED WITH CARE" — a permissividade do ToS da BN
continua valendo — mas o torna **inaplicável na prática a um cliente
puramente scriptado** contra o DocReader especificamente: a barreira não é
jurídica, é uma fricção de acesso interativa deliberada, e contorná-la
programaticamente (OCR/ML) seria um ato de natureza diferente do que foi
autorizado. Por isso, os títulos hdbn (Jornal do Commercio, Diário do Rio
de Janeiro, Gazeta de Notícias) não foram baixados por script nesta fase —
ver §2.

## 2. Resultados da sonda

Fonte: `docs/g0-inventory.md` e `.superpowers/sdd/2026-08-31-weather-rescue-brazil-g0-g1/task-5-report.md`. Sonda executada com `scripts/pull_probe.py`, requisições sequenciais, delay ≥2s, User-Agent identificado, R$0 gasto.

| fonte | itens baixados | tamanho em disco |
|---|---|---|
| DocVirt — Revista do Observatório (docId 14, Tomo I / 1886) | 28 imagens de página (`.webp`) | 6,3 MB |
| DocVirt — Annales de l'Observatoire Impérial (docId 3) | 1 imagem de página (beco sem saída, ver abaixo) | 50 KB |
| IAG-USP — Boletim Climatológico Anual 2010 (`.pdf`, ~54 páginas internas) | 1 arquivo | 2,9 MB |
| IAG-USP — Boletim Climatológico Anual 2020 (`.pdf`, ~40 páginas internas) | 1 arquivo | 2,3 MB |
| **Total** | **31 arquivos** (30 imagens/PDFs + sidecars de atribuição) | **~11 MB** |
| hdbn (Jornal do Commercio, Diário do Rio, Gazeta de Notícias) | **0** — não tentado, por desenho (CAPTCHA) | — |

Contando as páginas internas dos dois PDFs (~94), a sonda cobre ~122
páginas subjacentes em 31 arquivos — dentro do alvo de ~30-50 "page
images/PDF pages" quando a paginação interna dos PDFs é contada; 31 se a
leitura for por item baixado literalmente.

**Esquema de endereçamento do DocVirt** (descoberto por engenharia reversa
via browser instrumentado, confirmado depois com `httpx.get()` puro, sem
sessão):

```
GET https://api.docvirt.com/v1/documents/{collection}/{docId}/{page}
```

`collection="obnacional"`; `docId=14` = Revista do Observatório (216
páginas no volume, confirmado pelo contador do próprio viewer); `docId=3`
= Annales. Retorna os bytes da imagem diretamente (`image/webp`, HTTP 200),
sem cookies, sem header de auth, sem CAPTCHA. Nenhum CAPTCHA foi encontrado
em lugar nenhum do SPA do DocVirt (checado por grep no bundle JS
minificado inteiro — o único hit é um widget `react-google-recaptcha` não
relacionado, no formulário de contato do site).

**Beco sem saída dos Annales** (docId 3): a API serve apenas a página 1;
a página 2 retorna `HTTP 422 {"sucesso":false,"mensagem":"documentnotfound"}`
— resposta real da API, não bug do cliente (o mesmo padrão de requisição
funciona normalmente para docId=14 até a página 216). Parece ser uma
entrada de capa/stub no acervo, não um volume digitalizado. Documentado,
não perseguido further, conforme instrução do brief ("se hostil a script,
documentar e seguir").

## 3. Tabela de inventário completa

Fonte: `docs/g0-inventory.md` ("## Scoring table"), incluindo a coluna de direitos.

| candidato | período coberto | tabela encontrada? | variáveis | consistência de layout (1-5) | legibilidade (1-5) | somas mensais impressas? | fricção de acesso | páginas est., série completa | direitos | veredito de valor para treino |
|---|---|---|---|---|---|---|---|---|---|---|
| **Revista do Observatório** (DocVirt, docId 14+) | 1886-1891 (3 tomos; 193p+188p+164p ≈ 545 páginas impressas no total; esta tarefa buscou apenas o Tomo I, 216 páginas de scan) | **Sim** — tabela numérica diária completa mensal (barômetro, temp máx/mín/média, tensão de vapor, umidade, vento dir+força, nebulosidade, chuva, evaporação, ozônio) | T (máx/mín/média), pressão, tensão de vapor, umidade, vento dir+força, nebulosidade, precipitação, evaporação, ozônio — o conjunto mais amplo entre os candidatos | **5** — tipografia/cabeçalho de 2 colunas idêntica confirmada nas páginas 1, 22, 40 e 170-179 (~90% do volume) | **5** — scan limpo, tipo serifado nítido, sem desbotamento | **Sim** — tabela "Revista climatologica do mez" compara normais mensais com os valores do mês corrente, um cross-check embutido | **Nenhuma** — sem CAPTCHA, sem auth, GET simples | ~545 (3 tomos) se todos forem tão digitalizados quanto o Tomo I (não confirmado para Tomo II/III) | obra de 1886, PD pela Lei 9.610 (>70 anos); instituto federal (Observatório Nacional), acervo aberto, sem banner de direitos | **Melhor candidato encontrado nesta tarefa.** Conjunto de variáveis mais rico, maior legibilidade, fricção de acesso zero, tabela de checksum embutida. Série v1 recomendada. |
| Annales de l'Observatoire Impérial (DocVirt, docId 3) | Desconhecido (só 1 página servida) | Desconhecido | Desconhecido | N/A (1 página) | 5 (a única página vista) | Desconhecido | Nenhuma em princípio, mas **o conteúdo em si é indisponível** além da página 1 | Desconhecido, provavelmente pequeno | mesmo acervo federal do Revista, PD, sem banner de direitos | **Inviável** — páginas digitalizadas insuficientes para avaliar, muito menos treinar. Beco sem saída, documentado. |
| Boletim Climatológico Anual (IAG-USP, 1997-2025) | 1997-2025 (esta tarefa buscou 2010 + 2020) | **Sim** — tabelas diárias completas por ano, mais tabelas de resumo/recorde mensais e anuais | T, precipitação, umidade, vento, pressão, fenômenos (neblina/geada/granizo/trovoada), irradiação solar/insolação — conjunto muito amplo, instrumentação moderna | **5** — mesmo template institucional numa lacuna de 10 anos | **5 (trivial)** — nascido digital, não escaneado; não há problema de OCR | **Sim**, extensivamente (tabelas de recorde, médias mensais, série anual) | **Nenhuma** — download HTTPS simples, sem CAPTCHA (com o intermediário TLS empacotado) | ~29 PDFs (1997-2025) a ~40-55 páginas cada ≈ 1.200-1.600 páginas | universidade pública (USP), UI de download de PDF aberta, sem paywall/CAPTCHA; ainda protegido por direitos autorais (não é PD, publicado 1997-2025) mas publicado abertamente para reuso | **Alta legibilidade, mas baixo valor de "resgate"** — este dado já é totalmente digital e mantido ativamente pela USP; não está em risco. Melhor uso como conjunto de validação/referência para trabalho de estrutura de tabela, não como corpus de treino primário. |
| Jornal do Commercio (hdbn, `bib=364568`) | 1827-2016 (20 sub-bibliotecas de década, ~990.344 páginas totais) | Presumido sim para ao menos algumas edições (não confirmado nesta tarefa — bloqueado por CAPTCHA; Task 4 confirmou uma capa real, não uma tabela meteorológica) | Desconhecido até desbloqueio | Desconhecido até desbloqueio (jornal diário ao longo de 189 anos quase certamente muda de layout/tipografia repetidamente) | Desconhecido até desbloqueio; a amostra única da Task 4 foi um scan limpo e legível | Desconhecido | **Alta** — CAPTCHA obrigatório por documento (a partir de 03/10/2025); scripting totalmente bloqueado; precisa de um humano para desbloquear, por documento, fora de banda | Maior de longe se utilizável (990k páginas na corrida inteira; uma fatia estreita de 1850-1890 ainda seria substancial) | extinto em 2016; ex-**Diários Associados** (grupo de mídia ativo), risco de banner DA possível; edições do período-alvo (1850-90) são PD pela Lei 9.610 | **Maior volume teórico, mas atualmente não-scriptável.** Não pode ser pontuado nos critérios de tabela/variável/consistência sem o dono desbloquear documentos de amostra manualmente. Risco de aviso de direitos do grupo DA anotado acima. |
| Diário do Rio de Janeiro (hdbn, `bib=094170`) | 1821-1878 (2 sub-bibliotecas: 094170_01 1821-1858, 094170_02 1860-1878) | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido | **Alta** — mesmo portão de CAPTCHA | Desconhecido; corrida mais curta que a do Jornal do Commercio (57 anos vs. 189) | extinto em 1878, sem marca de direitos ativa; PD pela Lei 9.610 (>70 anos) | **Não pontuado até desbloqueio.** Menor fricção de direitos dos três títulos hdbn (totalmente extinto, sem dono ativo), se algum dia desbloqueado. |
| Gazeta de Notícias (hdbn, `bib=103730`) | 1875-1942/1956 (fontes divergem sobre o ano final exato; sub-bibliotecas por década) | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido até desbloqueio | Desconhecido | **Alta** — mesmo portão de CAPTCHA | Desconhecido | extinto em 1942/1956 (fontes divergem), sem marca de direitos ativa; PD pela Lei 9.610 (>70 anos) | **Não pontuado até desbloqueio.** Valor literário/histórico notável (Machado de Assis escreveu para o jornal 1883-1900), irrelevante para a missão meteorológica deste projeto; pontuado puramente por potencial de tabela meteorológica, desconhecido até desbloqueio. |

## 4. Série v1 recomendada

**Revista do Observatório** (DocVirt, `docId=14`+, `collection=obnacional`),
começando pelo Tomo I confirmado (1886). Razões (`docs/g0-inventory.md`,
"Recommended v1 series"): é o único candidato totalmente avaliado
ponta-a-ponta nesta tarefa — fricção de acesso zero (sem CAPTCHA, `httpx.get`
simples, TLS já corrigido e commitado), o conjunto de variáveis mais amplo
confirmado entre os candidatos (9 variáveis meteorológicas distintas mais
uma tabela de cross-check de normais mensais embutida), legibilidade
perfeita, e consistência de layout confirmada em ~90% da extensão do
volume. Também carrega valor de resgate real (diferente dos PDFs do
IAG-USP): é um arquivo físico de 138 anos raramente consultado fora de
círculos especializados, digitalizado uma vez pelo DocVirt sem garantia de
manutenção contínua.

**Ressalva honesta**: o Jornal do Commercio tem volume muito maior
(990.344 páginas na corrida completa vs. ~545 em 3 tomos da Revista) e, se
o CAPTCHA da hdbn se revelar desbloqueável por década em vez de por edição
(ver questão aberta (a) abaixo), pode superar a Revista do Observatório em
volume bruto o suficiente para justificar reabrir a escolha. Mas hoje ele
não pode ser pontuado em nenhum dos critérios de treino (tabela,
variáveis, consistência, legibilidade) porque está bloqueado por CAPTCHA —
a recomendação atual é baseada em "o que pode ser avaliado agora", não em
"o que teria mais dados se desbloqueado".

## 5. Questões abertas para o dono decidir

**(a) Granularidade do CAPTCHA da Hemeroteca — por sub-biblioteca de
década ou por edição?** Isso muda a viabilidade futura do Jornal do
Commercio como corpus (se por década: ~20 CAPTCHAs resolvem toda a
história do título; se por edição: a contagem escala para centenas/milhares).
A Task 4 confirmou que resolver o CAPTCHA para `364568_09` (década
1900-1909) não isentou `364568_04` (década 1850-1859) — mas isso só prova
que o portão é por-década-ou-mais-fino, não distingue "por sub-biblioteca
inteira" de "por edição dentro da mesma década". Teste de ~5 minutos, no
seu próprio browser:

1. Abra `https://memoria.bn.gov.br/docreader/DocReader.aspx?bib=364568_09&pagfis=1`
   (Jornal do Commercio, década 1900-1909, primeira página da
   sub-biblioteca). Resolva o CAPTCHA de 3 dígitos que aparecer.
2. Depois de desbloqueado, edite a URL trocando apenas o número de
   `pagfis` para um valor bem mais alto dentro da mesma sub-biblioteca —
   por exemplo `pagfis=5000` (lembrando que `pagfis` é um contador
   absoluto de página através de todas as edições daquela década, então um
   salto grande deve cair em uma edição diferente da que você acabou de
   ver). Navegue para
   `https://memoria.bn.gov.br/docreader/DocReader.aspx?bib=364568_09&pagfis=5000`.
3. **Observe**: a imagem da página carrega direto, ou um novo CAPTCHA
   aparece? Se carregar direto → o portão é por sub-biblioteca de década
   (bom para o projeto: ~20 desbloqueios cobrem tudo). Se pedir novo
   CAPTCHA → é por edição (ruim: a contagem de CAPTCHAs escala com o
   número de edições).

**(b) Confirmar a escolha da série v1** — Revista do Observatório, Tomo I,
conforme §4 acima, ou pedir que se investigue mais antes (ex.: localizar
os `docId` dos Tomos II/III, ainda não descobertos pelo probe).

**(c) Direitos — contexto do aviso da DA Press.** O Jornal do Commercio é
ex-Diários Associados (grupo ativo até hoje). Isso **não** re-copyrighta
o material de 1850-1890: esse material é domínio público por lei (Lei
9.610, regra dos 70 anos), independentemente de qualquer banner de marca
que a DA ou a própria BN coloquem por cima. Os únicos direitos que
persistem indefinidamente são os **direitos morais** (atribuição ao autor
e à fonte) — e essa atribuição já está embutida automaticamente nos
sidecars `.json` gerados ao lado de cada arquivo baixado (ver
`docs/g0-inventory.md`, seção "Rights column"). Ou seja: um banner de
direitos da DA, se aparecer, é um aviso comercial sem efeito legal sobre
o uso do material pré-1955 para este projeto — vale documentar mas não
muda a análise de viabilidade.

## 6. Gasto até aqui

**R$0,00 / US$0,00.** Nenhuma chamada de API paga foi feita em nenhuma das
tarefas do G0 (Task 2-5): todas as buscas usaram `httpx`/browser gratuitos
contra endpoints públicos. `data/ledger.json` — o arquivo que registraria
qualquer gasto de API, conforme a convenção do projeto — **não existe**
neste repositório, confirmando que não há nada a debitar.

## 7. Pedido

Aprovar a série **Revista do Observatório** (DocVirt) como corpus v1 e
abrir o gate **G1 (teto US$10)**? Ou matar o projeto aqui?
