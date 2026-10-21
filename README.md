# BB Restock 2.0

Mod para **Bloodborne** no PC ([bbport](https://github.com/Supermedo/bloodborne_pc)
ou [shadPS4](https://github.com/shadps4-emu/shadPS4)) que completa seus Blood Vials
e Quicksilver Bullets até o máximo toda vez que a área carrega.

> **Status:** testado no jogo (versão 1.09, bbport). Relatos de funcionamento em
> outras configurações são bem-vindos via *issues*.

## Requisitos

- Bloodborne **CUSA03173, versão 1.09** do jogo (a mesma exigida pelo bbport).
  **Não use em outras versões**: o arquivo substituído pode quebrar eventos do jogo.
- bbport ou shadPS4.
- Para gerar o mod com o script: Python 3.8 ou mais recente (só a biblioteca
  padrão) e os arquivos do jogo extraídos (a pasta que contém `dvdroot_ps4`).

## O que faz

Toda vez que a área carrega (respawn após morrer, viagem por lanterna, carregar
o save), seus **Blood Vials** e **Quicksilver Bullets** são completados até o
máximo (20 de cada). Só entra o que falta, direto no inventário, sem a janela
de "item recebido". Nada vai para o Armazém. Chega de farmar.

## Instalação

Este repositório **não contém arquivos do jogo**. Primeiro gere o mod a partir
da sua cópia do Bloodborne (veja [Gerar o mod](#gerar-o-mod)); o resultado é a
pasta `BB_Restock_Mod`.

### bbport (recomendado: não altera os arquivos do jogo)

1. Copie a pasta do mod para dentro da pasta `mods` do bbport. Se ela não
   existir, crie-a ao lado do `Bloodborne.exe`:

   ```
   bbport-windows\
   ├── Bloodborne.exe
   └── mods\
       └── BB_Restock_Mod\
           ├── dvdroot_ps4\ ...
           └── LEIA-ME.txt
   ```

2. Abra o `Bloodborne.exe` (launcher) e confira na aba **Mods & patches** que o
   mod aparece ativado. Pronto.

**Desinstalar:** apague a pasta do mod em `mods\` (ou desative no launcher).

### shadPS4 (ou sem bbport)

1. Faça backup deste arquivo da pasta do jogo (`CUSA03173`):
   `dvdroot_ps4\event\common.emevd.dcx`.
   Se você usa uma pasta de update separada (ex.: `CUSA03173-UPDATE`), o
   arquivo dela tem prioridade: faça o backup e copie para **ela**.
2. Copie a pasta `dvdroot_ps4` do mod por cima da pasta `dvdroot_ps4` do jogo,
   substituindo o arquivo.

**Desinstalar:** restaure o arquivo do backup (ou o `.bak` criado pelo `--install`).

### Em outros PCs

Basta copiar a pasta do mod gerada: não é preciso rodar o script de novo. O PC
de destino precisa ter a **mesma versão do jogo** (1.09).

## Compatibilidade

- O mod substitui um único arquivo: `dvdroot_ps4\event\common.emevd.dcx`.
  Ele conflita com qualquer outro mod que substitua esse mesmo arquivo; só um
  dos dois vai funcionar. No bbport, vale o mod carregado por último na aba
  **Mods & patches**.
- Mods que alteram outros arquivos (params, modelos, mapas, texturas)
  funcionam juntos.

## Observações

- Se você tiver mais que 20 (por exemplo com uma runa que aumenta o limite), o
  mod não entrega nada daquele item. Para completar até outro número, gere o
  mod com `--vials`/`--bullets`.
- Itens que já estiverem no Armazém continuam lá; o mod só não adiciona mais.

## Histórico de versões

- **2.0**: completa até o máximo em vez de entregar 20 por carregamento: só o
  que falta, direto no inventário, sem janela e sem nada para o Armazém. Agora
  só o `common.emevd.dcx` é alterado (o gameparam não é mais necessário).
- **1.0**: primeira versão: 20 Blood Vials e 20 Quicksilver Bullets por
  carregamento, com o excedente indo para o Armazém.

---

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
`tenho >= máximo` evita que a subtração fique negativa.

As variáveis ficam nos valores de evento de 8 bits em `6960`, `6970`, `6980` e
`6990`. Nenhum evento ou script de diálogo do jogo usa a faixa `6960–6999`, e
o script recusa a operação se o `common.emevd` usar alguma delas.

### Detalhes técnicos

- **DCX:** descomprimido e recomprimido com zlib (DFLT), mantendo o cabeçalho original.
- **EMEVD:** o arquivo é interpretado e regravado no layout do Bloodborne
  (64-bit, versão `0xCC`). Antes de qualquer alteração, o script confirma que a
  regravação preserva o conteúdo. Os índices de parâmetros do evento 0 são
  ajustados pela instrução inserida.

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
