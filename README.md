# BB Restock

Mod para **Bloodborne** rodando no PC via [shadPS4](https://github.com/shadps4-emu/shadPS4):
toda vez que a área carrega, você recebe **Blood Vials** e **Quicksilver Bullets**.
Isso inclui o respawn após morrer, a viagem por lanterna e o carregamento do save.
O que passar do limite do inventário vai para o Armazém, então você sempre volta
com o inventário cheio e não precisa mais farmar.

Este repositório **não contém arquivos do jogo**. Ele traz um script que gera o
mod a partir da sua própria cópia do Bloodborne.

> **Status:** os formatos de arquivo foram verificados com testes automatizados
> (veja [Testes](#testes)), mas o mod ainda **não foi validado dentro do jogo**.
> Relatos de funcionamento são bem-vindos via *issues*.

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
    ├── event/common.emevd.dcx
    └── param/gameparam/gameparam.parambnd.dcx
```

| Opção | Padrão | Descrição |
|---|---|---|
| `--vials N` | 20 | Blood Vials entregues por carregamento (1–99) |
| `--bullets N` | 20 | Quicksilver Bullets entregues por carregamento (1–99) |
| `--out PASTA` | `BB_Restock_Mod` | Pasta de saída |
| `--install` | desligado | Também instala no jogo, salvando os originais como `.bak` |

Se os arquivos tiverem um formato inesperado ou já tiverem sido modificados, o
script para com uma mensagem de erro e não grava nada.

## Instalar (em qualquer PC)

1. Faça backup destes dois arquivos do jogo:
   - `dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx`
   - `dvdroot_ps4/event/common.emevd.dcx`
2. Copie a pasta `dvdroot_ps4` gerada por cima da `dvdroot_ps4` do jogo.

Para instalar em outros PCs, basta copiar os mesmos dois arquivos. O PC de
destino precisa ter a **mesma versão do jogo** (mesmo update e DLC) usada para
gerar o mod. Se a versão for diferente, gere o mod de novo naquele PC.

**Desinstalar:** restaure os dois arquivos originais (ou os `.bak`).

## Como funciona

O mod adiciona duas coisas ao jogo:

1. **`ItemLotParam`** (em `gameparam.parambnd.dcx`): dois "lotes de itens" novos.

   | Lote | Item | Categoria | Chance | Flag de coleta |
   |---|---|---|---|---|
   | `9990000` | Blood Vial (`1000`) | Goods (`4`) | 100% | nenhuma (`-1`) |
   | `9990002` | Quicksilver Bullets (`900`) | Goods (`4`) | 100% | nenhuma (`-1`) |

   Sem flag de coleta, o lote pode ser recebido infinitas vezes. Os IDs
   `9990001` e `9990003` ficam livres de propósito: o jogo entrega lotes de
   IDs consecutivos em cadeia.

2. **`common.emevd`**: um evento novo (`9990000`) que executa `AwardItemLot`
   nos dois lotes. Ele é inicializado no começo do evento `0`, que o jogo
   executa a cada carregamento de área.

O jogo já repõe frascos e balas a partir do Armazém ao morrer ou descansar. O
mod garante que sempre haja estoque.

### Detalhes técnicos

- **DCX:** descomprimido e recomprimido com zlib (DFLT), mantendo o cabeçalho original.
- **BND4:** o `ItemLotParam.param` modificado é anexado ao fim do arquivo e só o
  cabeçalho dele é atualizado. Nomes, tabela de hash e os demais params ficam intactos.
- **PARAM:** as linhas novas são inseridas em ordem de ID. Todas as linhas
  originais são relidas e comparadas byte a byte após a gravação.
- **EMEVD:** o arquivo é interpretado e regravado no layout do Bloodborne
  (64-bit, versão `0xCC`). Antes de qualquer alteração, o script confirma que a
  regravação preserva o conteúdo. Os índices de parâmetros do evento 0 são
  ajustados pela instrução inserida.

## Limitações conhecidas

- A entrega também acontece em viagens por lanterna e ao carregar o save, não só ao morrer.
- Pode aparecer o aviso de "item recebido" a cada carregamento.
- O Armazém tem um limite; o que passar dele é perdido.
- Feito para a versão de PS4 usada no shadPS4. Outras versões podem ter um
  `ItemLotParam` diferente; nesse caso o script recusa a operação.

## Testes

`tests/run_tests.sh` faz um teste de ponta a ponta:

1. Gera, com a [SoulsFormatsNEXT](https://github.com/soulsmods/SoulsFormatsNEXT),
   arquivos sintéticos no formato do Bloodborne, em 4 variações de cabeçalho PARAM/BND4.
2. Roda o `bb_restock.py` sobre eles.
3. Relê o resultado com a SoulsFormats e verifica que:
   - as linhas, arquivos e eventos originais não mudaram;
   - os lotes e o evento novos estão corretos;
   - rodar o script sobre arquivos já modificados é recusado.

Requer `git`, `python3` e .NET SDK 8 ou mais recente:

```
bash tests/run_tests.sh
```

## Créditos

- [SoulsFormatsNEXT](https://github.com/soulsmods/SoulsFormatsNEXT): referência
  dos formatos DCX, BND4, PARAM e EMEVD; usada nos testes.
- [Smithbox](https://github.com/vawser/Smithbox): definições de params do Bloodborne.
- [DarkScript3](https://github.com/AinTunez/DarkScript3): definições das instruções EMEVD.

## Licença

[MIT](LICENSE). Bloodborne é propriedade da Sony Interactive Entertainment e da
FromSoftware. Este projeto não é afiliado a elas e não distribui conteúdo do jogo.
