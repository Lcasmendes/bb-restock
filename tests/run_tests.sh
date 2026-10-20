#!/usr/bin/env bash
# Teste de ponta a ponta: gera arquivos sinteticos com a SoulsFormats, roda o
# bb_restock.py e verifica o resultado com a SoulsFormats.
# Requer: git, python3, .NET SDK 8+.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEPS="$HERE/.deps"
WORK="$HERE/.work"
mkdir -p "$DEPS"

if [ ! -d "$DEPS/SoulsFormatsNEXT" ]; then
  git clone -q --depth 1 https://github.com/soulsmods/SoulsFormatsNEXT "$DEPS/SoulsFormatsNEXT"
fi
if [ ! -d "$DEPS/Smithbox" ]; then
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/vawser/Smithbox "$DEPS/Smithbox"
  git -C "$DEPS/Smithbox" sparse-checkout set --no-cone 'src/Smithbox.Data/Assets/PARAM/BB/Defs/*'
fi

# Compila a SoulsFormats com o SDK instalado (o projeto pede net9.0).
SDK_MAJOR="$(dotnet --version | cut -d. -f1)"
TARGET="net${SDK_MAJOR}.0"
SF_PROJ="$DEPS/SoulsFormatsNEXT/SoulsFormats/SoulsFormats.csproj"
sed -i "s#<TargetFramework>net[0-9.]*</TargetFramework>#<TargetFramework>${TARGET}</TargetFramework>#" "$SF_PROJ"

dotnet build "$HERE/verify/verify.csproj" -nologo -v q \
  -p:SoulsTarget="$TARGET" -p:SoulsFormatsProj="$SF_PROJ" -o "$WORK/bin" >/dev/null

export BB_ITEMLOT_DEF="$DEPS/Smithbox/src/Smithbox.Data/Assets/PARAM/BB/Defs/ItemLotParam.xml"
VERIFY="$WORK/bin/verify.dll"

for v in 0 1 2 3; do
  rm -rf "$WORK/t$v"
  dotnet "$VERIFY" gen "$WORK/t$v/game" "$v"
  python3 -I "$HERE/../bb_restock.py" "$WORK/t$v/game" --out "$WORK/t$v/mod" --vials 20 --bullets 15 >/dev/null
  dotnet "$VERIFY" verify "$WORK/t$v/game" "$WORK/t$v/mod" 20 15
done

# Rodar sobre arquivos ja modificados deve falhar sem gerar nada.
if python3 -I "$HERE/../bb_restock.py" "$WORK/t0/mod" --out "$WORK/t0/mod2" 2>/dev/null; then
  echo "FALHA: patch duplo foi aceito"; exit 1
fi
echo "TODOS OS TESTES PASSARAM"
