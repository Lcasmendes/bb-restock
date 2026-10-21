# BB Restock

Mod para **Bloodborne** rodando no PC via [shadPS4](https://github.com/shadps4-emu/shadPS4)
ou bbport: toda vez que a área carrega, seus **Blood Vials** e **Quicksilver Bullets**
são completados até o máximo. Isso inclui o respawn após morrer, a viagem por
lanterna e o carregamento do save. Só entra o que falta, direto no inventário:
nada vai para o Armazém e você não precisa mais farmar.

Este repositório **não contém arquivos do jogo**. Ele traz um script que gera o
mod a partir da sua própria cópia do Bloodborne.

> **Status:** testado no jogo (versão 1.09, bbport). Os formatos de arquivo também
> são verificados com testes automatizados (veja [Testes](#testes)).
> Relatos de funcionamento em outras configurações são bem-vindos via *issues*.

## Requisitos

- Python 3.8 ou mais recente (só a biblioteca padrão)
- Os arquivos do jogo extraídos (a pasta que contém `dvdroot_ps4`)

## Gerar o mod

```
python bb_restock.py "C:\caminho\do\jogo\CUSA03173"
```

Você pode passar a pasta que contém `dvdroot_ps4` ou a própria `dvdroot_ps4`.
Os arquivos originais **não são alterados**. O mod é gravado em `BB_Restock_Mod/`:

```
BB_Restock_Mod/
├── LEIA-ME.txt
└── dvdroot_ps4/
    └── event/common.emevd.dcx
```

| Opção | Padrão | Descrição |
|---|---|---|
| `--vials N` | 20 | Completar Blood Vials até N (1–99; 20 é o máximo do jogo) |
| `--bullets N` | 20 | Completar Quicksilver Bullets até N (1–99; 20 é o máximo do jogo) |
| `--out PASTA` | `BB_Restock_Mod` | Pasta de saída |
| `--install` | desligado | Também instala no jogo, salvando o original como `.bak` |

Se o arquivo tiver um formato inesperado ou já tiver sido modificado, o
script para com uma mensagem de erro e não grava nada.

## Instalar (em qualquer PC)

**bbport:** copie a pasta gerada para `bbport-windows\mods\` (uma pasta por mod).
O launcher ativa o mod sozinho, e os arquivos do jogo não são alterados.

**shadPS4:**

1. Faça backup de `dvdroot_ps4/event/common.emevd.dcx`.
2. Copie a pasta `dvdroot_ps4` gerada por cima da `dvdroot_ps4` do jogo.

Para instalar em outros PCs, basta copiar o mesmo arquivo. O PC de destino
precisa ter a **mesma versão do jogo** (mesmo update e DLC) usada para gerar
o mod. Se a versão for diferente, gere o mod de novo naquele PC.

**Desinstalar:** apague a pasta do mod (bbport) ou restaure o arquivo original (`.bak`).

## Como funciona

O mod adiciona um evento novo (`9990000`) ao `common.emevd` e o inicializa no
começo do evento `0`, que o jogo executa a cada carregamento de área. Para cada
item, o evento faz:

```
quero   = máximo                                   2003[41] Event Value Operation (atribuir)
tenho   = quantidade no inventário                 2003[42] Store Item Amount Held in Event Value
se tenho >= máximo: pula as duas próximas          3[12] IF Event Value + 1000[01] SKIP
quero   = quero - tenho                            2003[41] Event Value Operation (subtrair)
entrega "quero" unidades direto no inventário      2003[43] Directly Give Player Item
```

É o mesmo padrão que o próprio jogo usa no evento `12101021` de
`m21_00_00_00.emevd` para completar Quicksilver Bullets. A verificação
`tenho >= máximo` evita que a subtração fique negativa (por exemplo, com uma
runa que aumenta o limite).

As variáveis ficam nos valores de evento de 8 bits em `6960`, `6970`, `6980` e
`6990`. Nenhum evento ou script de diálogo do jogo usa a faixa `6960–6999`, e
o script recusa a operação se o `common.emevd` usar alguma delas.

### Detalhes técnicos

- **DCX:** descomprimido e recomprimido com zlib (DFLT), mantendo o cabeçalho original.
- **EMEVD:** o arquivo é interpretado e regravado no layout do Bloodborne
  (64-bit, versão `0xCC`). Antes de qualquer alteração, o script confirma que a
  regravação preserva o conteúdo. Os índices de parâmetros do evento 0 são
  ajustados pela instrução inserida.

## Limitações conhecidas

- A reposição também acontece em viagens por lanterna e ao carregar o save, não só ao morrer.
- Com uma runa que aumenta o limite acima de 20, gere o mod com `--vials`/`--bullets` maiores.
- Itens que já estão no Armazém continuam lá; o mod só não adiciona mais.
- Feito para a versão 1.09 de PS4 usada no shadPS4/bbport.

## Testes

`tests/run_tests.sh` faz um teste de ponta a ponta:

1. Gera, com a [SoulsFormatsNEXT](https://github.com/soulsmods/SoulsFormatsNEXT),
   arquivos sintéticos no formato do Bloodborne.
2. Roda o `bb_restock.py` sobre eles.
3. Relê o resultado com a SoulsFormats e verifica que:
   - os eventos originais não mudaram;
   - o evento novo e a inicialização no evento 0 estão corretos;
   - rodar o script sobre arquivos já modificados é recusado.

Requer `git`, `python3` e .NET SDK 8 ou mais recente:

```
bash tests/run_tests.sh
```

## Créditos

- [SoulsFormatsNEXT](https://github.com/soulsmods/SoulsFormatsNEXT): referência
  dos formatos DCX e EMEVD; usada nos testes.
- [DarkScript3](https://github.com/AinTunez/DarkScript3): definições das instruções EMEVD.

## Licença

[MIT](LICENSE). Bloodborne é propriedade da Sony Interactive Entertainment e da
FromSoftware. Este projeto não é afiliado a elas e não distribui conteúdo do jogo.
