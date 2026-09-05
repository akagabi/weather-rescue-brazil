# Workbench de transcrição — rotular e revisar qualquer tabela

```
python -m wrb.serve      # abre em http://127.0.0.1:8765
```

Tudo local: o navegador é só a interface, o modelo roda nesta máquina, nada sai daqui.

## O que ele é

Uma tela dirigida por **perfis** (`wrb.profile`). Nada nele conhece a Revista: uma publicação é
o seu perfil (as colunas impressas) mais as imagens das páginas. A mesma tela serve Corumbá, uma
folha de Santa-Cruz ou uma publicação adicionada amanhã — basta um JSON em `profiles/`.

O laço que ele existe para sustentar, por publicação nova:

| passo | tempo |
|---|---|
| digitar ~50 linhas com a imagem à frente | ~20 min |
| treinar um adaptador com elas (`Treinar`) | ~20 min no M4 |
| o modelo rascunha o resto; você corrige só o que o QC marcar | resto da tarde |

## Como usar

1. Escolha publicação, documento, página e período. A URL é um link direto
   (`/?profile=corumba-1889&doc=16&page=72&period=1889-12`), então uma página específica pode ser
   compartilhada ou enfileirada.
2. Cada linha aparece como o **recorte impresso** com os campos logo abaixo, na mesma rolagem
   horizontal — o valor impresso fica em cima do campo onde ele deve ser digitado.
3. **Enter** pula para a mesma coluna da linha seguinte (digitar uma coluna inteira de uma vez é
   mais rápido do que linha a linha). **Tab** anda pelas colunas.
4. Gravação é automática (700 ms após parar de digitar), em `data/labels/<perfil>/<doc>_<pág>.json`
   — arquivos simples, versionáveis, e é o mesmo formato que o treino consome.
5. Valores fisicamente impossíveis acendem em vermelho na hora, usando as faixas do perfil (a
   verificação que o modelo comprovadamente não faz sozinho — ver `docs/gates/g3-report.md`).
6. **Treinar** dispara o LoRA com o que estiver rotulado (recusa abaixo de 20 linhas).

## Quando a página não fecha

Se o localizador não fechar o número de linhas esperado, a tela avisa e **mostra mesmo assim** o
que encontrou, para revisão humana em vez de recusa silenciosa. Confira se cada recorte contém uma
linha só antes de rotular.

## Adicionar uma publicação

Escreva `profiles/<id>.json` — veja `wrb.profile.Profile` para os campos e
`profiles/corumba-1889.json` como exemplo de layout bem diferente (16 colunas, duas leituras por
dia, quatro colunas de texto livre). `wrb.profile.blank()` gera o esqueleto a partir dos rótulos
impressos das colunas.

## Adicionar uma publicação pela interface

Botão **+ Publicação**. Você cola os rótulos das colunas **como aparecem impressos**, um por
linha, da esquerda para a direita — incluindo a coluna do dia e as de texto. O perfil é criado na
hora e já aparece na lista; nenhum JSON é editado à mão. Depois registre as imagens em
`data/raw/docvirt/<doc>/000001.webp` (ou `POST /api/upload` com os caminhos dos arquivos).

## Um modelo, várias publicações

**Treinar** treina UM modelo com tudo que estiver rotulado, em todas as publicações — não um
modelo por publicação. Isso não é só arrumação: o motivo pelo qual o modelo falhou em Corumbá é
que 91% do treino era um único layout de 15 colunas, então ele decorou "15 células"
(`docs/g4-generalisation.md`). Ter dois ou três layouts na mistura é exatamente o que ensina a
contar colunas a partir da imagem. **Cada publicação que você rotula melhora o modelo para a
próxima.**

O caminho é: rótulos → `data/g4/workbench_manifest.json` (cada exemplo carrega o próprio alvo,
no formato do seu perfil) → `scripts/g4_train.py --manifest`. O gold congelado continua fora do
treino, com a mesma guarda de vazamento de sempre.
