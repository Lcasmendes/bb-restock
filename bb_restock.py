#!/usr/bin/env python3
"""
BB Restock - Bloodborne (shadPS4 / bbport / dump de PS4)

Gera um mod que, toda vez que a area carrega (inclusive no respawn apos morrer),
completa os Blood Vials e as Quicksilver Bullets do inventario ate o maximo.
Entrega so o que falta: nada vai para o Armazem.

O que o script altera:
  event/common.emevd.dcx
    -> adiciona um evento novo que, para cada item, le a quantidade que o
       jogador carrega, calcula (maximo - quantidade) e entrega a diferenca
       direto no inventario. O evento e inicializado no evento 0, que roda a
       cada carregamento de area. E o mesmo padrao de instrucoes que o jogo
       usa no evento 12101021 de m21_00_00_00.emevd.

Os arquivos originais nunca sao modificados (a menos que use --install, que
faz backup .bak antes). Requer apenas Python 3.8+ (biblioteca padrao).

Uso:
  python bb_restock.py "C:\\caminho\\CUSA03173"
  python bb_restock.py "C:\\caminho\\CUSA03173" --vials 20 --bullets 20 --install
"""

import argparse
import os
import shutil
import struct
import sys
import zlib

# ----------------------------------------------------------------------------
# Constantes do Bloodborne
# ----------------------------------------------------------------------------

BLOOD_VIAL_ID = 1000          # EquipParamGoods (maxNum 20)
QUICKSILVER_BULLET_ID = 900   # EquipParamGoods (maxNum 20)
EMEVD_GOODS = 3               # ItemType "Goods" nas instrucoes de evento
RESTOCK_EVENT_ID = 9990000

# Valores de evento (8 flags cada) usados como variaveis temporarias.
# Faixa 6960-6999: nao usada por nenhum evento nem script de dialogo do jogo.
VALUE_BITS = 8
VIALS_WANT, VIALS_HELD = 6960, 6970
BULLETS_WANT, BULLETS_HELD = 6980, 6990

COMMON_EMEVD_REL = ("event", "common.emevd.dcx")


class PatchError(Exception):
    pass


# ----------------------------------------------------------------------------
# DCX (DFLT / zlib)
# ----------------------------------------------------------------------------

DCX_HEADER_SIZE = 0x4C


def dcx_decompress(data):
    """Retorna (header, payload). header e None se o arquivo nao for DCX."""
    if data[:4] != b"DCX\0":
        return None, data
    if data[0x18:0x1C] != b"DCS\0" or data[0x24:0x28] != b"DCP\0" or data[0x44:0x48] != b"DCA\0":
        raise PatchError("Cabecalho DCX inesperado.")
    if data[0x28:0x2C] != b"DFLT":
        raise PatchError("Compressao DCX %r nao suportada (esperado DFLT)." % data[0x28:0x2C])
    usize, csize = struct.unpack_from(">II", data, 0x1C)
    payload = zlib.decompress(data[DCX_HEADER_SIZE:DCX_HEADER_SIZE + csize])
    if len(payload) != usize:
        raise PatchError("Tamanho descomprimido do DCX nao confere.")
    return data[:DCX_HEADER_SIZE], payload


def dcx_compress(header, payload):
    if header is None:
        return payload
    comp = zlib.compress(payload, 9)  # 78 DA ... adler32, igual ao jogo
    h = bytearray(header)
    struct.pack_into(">II", h, 0x1C, len(payload), len(comp))
    return bytes(h) + comp


# ----------------------------------------------------------------------------
# EMEVD (formato Bloodborne: little-endian, 64-bit, versao 0xCC)
# ----------------------------------------------------------------------------

class Instr:
    def __init__(self, bank, idx, args=b"", layer=None):
        self.bank, self.id, self.args, self.layer = bank, idx, args, layer

    def key(self):
        return (self.bank, self.id, self.args, self.layer)


class Event:
    def __init__(self, eid, rest=0):
        self.id, self.rest, self.instrs, self.params = eid, rest, [], []

    def key(self):
        return (self.id, self.rest, [i.key() for i in self.instrs], list(self.params))


class Emevd:
    def __init__(self, data):
        if data[:4] != b"EVD\0":
            raise PatchError("Arquivo nao e EMEVD.")
        big, is64, unk06, unk07 = data[4], data[5], data[6], data[7]
        version = struct.unpack_from("<i", data, 8)[0]
        if not (big == 0 and is64 == 0xFF and unk06 == 0 and unk07 == 0 and version == 0xCC):
            raise PatchError("EMEVD nao esta no formato do Bloodborne.")
        v = struct.unpack_from("<16q", data, 0x10)
        (event_count, events_off, _ic, instrs_off, _uc, _u3, _lc, layers_off,
         _pc, params_off, linked_count, linked_off, _al, args_off, str_len, str_off) = v

        self.events = []
        for i in range(event_count):
            p = events_off + i * 48
            eid, icount, ioff, pcount = struct.unpack_from("<4q", data, p)
            poff = struct.unpack_from("<i", data, p + 32)[0]
            rest = struct.unpack_from("<I", data, p + 40)[0]
            ev = Event(eid, rest)
            for k in range(icount):
                q = instrs_off + ioff + k * 32
                bank, iid, alen = struct.unpack_from("<iiq", data, q)
                aoff = struct.unpack_from("<i", data, q + 16)[0]
                loff = struct.unpack_from("<i", data, q + 24)[0]
                args = data[args_off + aoff:args_off + aoff + alen] if alen > 0 else b""
                layer = None
                if loff != -1:
                    lp = layers_off + loff
                    if struct.unpack_from("<i", data, lp)[0] != 2:
                        raise PatchError("Layer EMEVD invalido.")
                    layer = struct.unpack_from("<I", data, lp + 4)[0]
                ev.instrs.append(Instr(bank, iid, args, layer))
            for k in range(pcount):
                ev.params.append(struct.unpack_from("<3qii", data, params_off + poff + k * 32))
            self.events.append(ev)
        self.linked = list(struct.unpack_from("<%dq" % linked_count, data, linked_off))
        self.strings = data[str_off:str_off + str_len]

    def write(self):
        layers = []
        for ev in self.events:
            for ins in ev.instrs:
                if ins.layer is not None and ins.layer not in layers:
                    layers.append(ins.layer)
        n_instr = sum(len(e.instrs) for e in self.events)
        n_param = sum(len(e.params) for e in self.events)

        header_end = 0x90
        events_off = header_end
        instrs_off = events_off + 48 * len(self.events)
        layers_off = instrs_off + 32 * n_instr
        layer_rel = {l: i * 32 for i, l in enumerate(layers)}
        args_off = layers_off + 32 * len(layers)

        args_blob = bytearray()
        arg_rel = []
        for ev in self.events:
            for ins in ev.instrs:
                if ins.args:
                    arg_rel.append(len(args_blob))
                    args_blob += ins.args
                    args_blob += b"\0" * (-(args_off + len(args_blob)) % 4)
                else:
                    arg_rel.append(-1)
        args_blob += b"\0" * (-len(args_blob) % 0x10)
        params_off = args_off + len(args_blob)
        linked_off = params_off + 32 * n_param
        str_off = linked_off + 8 * len(self.linked)
        file_size = str_off + len(self.strings)

        out = bytearray(b"EVD\0" + bytes([0, 0xFF, 0, 0]))
        out += struct.pack("<ii", 0xCC, file_size)
        out += struct.pack("<16q", len(self.events), events_off, n_instr, instrs_off,
                           0, layers_off, len(layers), layers_off, n_param, params_off,
                           len(self.linked), linked_off, len(args_blob), args_off,
                           len(self.strings), str_off)
        ins_index = 0
        param_index = 0
        for ev in self.events:
            ioff = ins_index * 32 if ev.instrs else -1
            poff = param_index * 32 if ev.params else -1
            out += struct.pack("<4qiiIi", ev.id, len(ev.instrs), ioff, len(ev.params), poff, 0, ev.rest, 0)
            ins_index += len(ev.instrs)
            param_index += len(ev.params)
        k = 0
        for ev in self.events:
            for ins in ev.instrs:
                loff = layer_rel[ins.layer] if ins.layer is not None else -1
                out += struct.pack("<iiqiiii", ins.bank, ins.id, len(ins.args), arg_rel[k], 0, loff, 0)
                k += 1
        for l in layers:
            out += struct.pack("<iIqqq", 2, l, 0, -1, 1)
        out += args_blob
        for ev in self.events:
            for prm in ev.params:
                out += struct.pack("<3qii", *prm)
        out += struct.pack("<%dq" % len(self.linked), *self.linked)
        out += self.strings
        assert len(out) == file_size
        return bytes(out)

    def key(self):
        return ([e.key() for e in self.events], self.linked, self.strings)


# ----------------------------------------------------------------------------
# Patch
# ----------------------------------------------------------------------------

CALC_SUB, CALC_ASSIGN = 1, 5        # Event Value Operation: tipo de calculo
CMP_GE = 4                          # Comparacao ">="


def topup_instrs(item_id, maximum, want, held, group):
    """Completa item_id ate `maximum`:
        want = maximum
        held = quantidade que o jogador carrega
        se held >= maximum: pula as duas proximas (evita valor negativo)
        want = want - held
        entrega `want` unidades direto no inventario"""
    if not 1 <= maximum <= 99:
        raise PatchError("Maximo deve estar entre 1 e 99.")
    return [
        Instr(2003, 41, struct.pack("<iIiiIb3x", want, VALUE_BITS, maximum, 0, 1, CALC_ASSIGN)),
        Instr(2003, 42, struct.pack("<iiiI", EMEVD_GOODS, item_id, held, VALUE_BITS)),
        Instr(3, 12, struct.pack("<b3xiBB2xI", group, held, VALUE_BITS, CMP_GE, maximum)),
        Instr(1000, 1, struct.pack("<BBbx", 2, 1, group)),   # SKIP 2 se o grupo for verdadeiro
        Instr(2003, 41, struct.pack("<iIiiIb3x", want, VALUE_BITS, 0, held, VALUE_BITS, CALC_SUB)),
        Instr(2003, 43, struct.pack("<iiiI", EMEVD_GOODS, item_id, want, VALUE_BITS)),
    ]


def patch_common_emevd(raw, vials, bullets):
    header, data = dcx_decompress(raw)
    emevd = Emevd(data)

    # A re-serializacao precisa preservar o conteudo antes de alterarmos algo.
    rewritten = emevd.write()
    if Emevd(rewritten).key() != emevd.key():
        raise PatchError("Verificacao falhou: EMEVD nao sobrevive a regravacao.")

    ids = [e.id for e in emevd.events]
    if RESTOCK_EVENT_ID in ids:
        raise PatchError("Evento %d ja existe. Os arquivos ja foram modificados? "
                         "Use os arquivos originais do jogo." % RESTOCK_EVENT_ID)
    if 0 not in ids:
        raise PatchError("Evento 0 nao encontrado no common.emevd.")
    used = set(ids)
    for ev in emevd.events:
        for ins in ev.instrs:
            for o in range(0, len(ins.args) - 3, 4):
                used.add(struct.unpack_from("<I", ins.args, o)[0])
    for base in (VIALS_WANT, VIALS_HELD, BULLETS_WANT, BULLETS_HELD):
        if used & set(range(base, base + VALUE_BITS)):
            raise PatchError("Flags %d-%d ja usadas pelo common.emevd; versao do jogo diferente?"
                             % (base, base + VALUE_BITS - 1))

    restock = Event(RESTOCK_EVENT_ID, rest=0)
    restock.instrs += topup_instrs(BLOOD_VIAL_ID, vials, VIALS_WANT, VIALS_HELD, 1)
    restock.instrs += topup_instrs(QUICKSILVER_BULLET_ID, bullets, BULLETS_WANT, BULLETS_HELD, 2)
    emevd.events.append(restock)

    ev0 = emevd.events[ids.index(0)]
    # InitializeEvent(slot 0, evento, 0) no inicio do evento 0
    ev0.instrs.insert(0, Instr(2000, 0, struct.pack("<iIi", 0, RESTOCK_EVENT_ID, 0)))
    ev0.params = [(p[0] + 1,) + tuple(p[1:]) for p in ev0.params]

    new_data = emevd.write()
    check = Emevd(new_data)
    if check.key() != emevd.key():
        raise PatchError("Verificacao falhou: EMEVD modificado.")
    return dcx_compress(header, new_data)


def find_file(root, rel_parts):
    """Procura dvdroot_ps4/<rel> (sem diferenciar maiusculas) a partir de root."""
    candidates = [root, os.path.join(root, "dvdroot_ps4")]
    for base in candidates:
        path = base
        ok = True
        for part in rel_parts:
            if not os.path.isdir(path):
                ok = False
                break
            match = [n for n in os.listdir(path) if n.lower() == part.lower()]
            if not match:
                ok = False
                break
            path = os.path.join(path, match[0])
        if ok and os.path.isfile(path):
            return path
    raise PatchError("Nao encontrei %s em %s. Passe a pasta do jogo (a que contem dvdroot_ps4)."
                     % ("/".join(rel_parts), root))


def write_readme(out_dir, vials, bullets):
    text = """BB Restock - mod para Bloodborne

Efeito: toda vez que a area carrega (respawn apos morte, viagem por lanterna,
carregar o save) seus Blood Vials sao completados ate {v} e suas Quicksilver
Bullets ate {b}. So entra o que falta, direto no inventario: nada vai para o
Armazem.

Instalacao (em qualquer PC com a MESMA versao do jogo):
  bbport:  copie esta pasta para dentro de bbport-windows\\mods\\
  shadPS4: faca backup de dvdroot_ps4\\event\\common.emevd.dcx do jogo e copie
           a pasta dvdroot_ps4 deste mod por cima da do jogo.

Desinstalar: apague a pasta do mod (bbport) ou restaure o arquivo original.
""".format(v=vials, b=bullets)
    with open(os.path.join(out_dir, "LEIA-ME.txt"), "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description="Gera o mod BB Restock para Bloodborne.")
    ap.add_argument("game_dir", help="Pasta do jogo (contem dvdroot_ps4) ou a propria dvdroot_ps4")
    ap.add_argument("--out", default="BB_Restock_Mod", help="Pasta de saida (padrao: BB_Restock_Mod)")
    ap.add_argument("--vials", type=int, default=20,
                    help="Completar Blood Vials ate este numero (padrao 20, o maximo do jogo)")
    ap.add_argument("--bullets", type=int, default=20,
                    help="Completar Quicksilver Bullets ate este numero (padrao 20, o maximo do jogo)")
    ap.add_argument("--install", action="store_true",
                    help="Tambem instala direto no jogo (cria .bak do original)")
    args = ap.parse_args()

    try:
        ev_path = find_file(args.game_dir, COMMON_EMEVD_REL)
        print("common.emevd: %s" % ev_path)
        with open(ev_path, "rb") as f:
            new_ev = patch_common_emevd(f.read(), args.vials, args.bullets)
        print("common.emevd: evento %d adicionado (completa frascos ate %d e balas ate %d)."
              % (RESTOCK_EVENT_ID, args.vials, args.bullets))

        dst = os.path.join(args.out, "dvdroot_ps4", *COMMON_EMEVD_REL)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(new_ev)
        write_readme(args.out, args.vials, args.bullets)
        print("Mod gerado em: %s" % os.path.abspath(args.out))

        if args.install:
            bak = ev_path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(ev_path, bak)
            with open(ev_path, "wb") as f:
                f.write(new_ev)
            print("Instalado no jogo (original salvo como .bak).")
    except PatchError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
