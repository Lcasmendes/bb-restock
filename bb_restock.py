#!/usr/bin/env python3
"""
BB Restock - Bloodborne (shadPS4 / dump de PS4)

Gera um mod que entrega Blood Vials e Quicksilver Bullets toda vez que a area
carrega (inclusive no respawn apos morrer). O excedente vai para o Armazem,
entao o inventario volta sempre cheio.

O que o script altera:
  1. param/gameparam/gameparam.parambnd.dcx
     -> adiciona 2 linhas em ItemLotParam (um lote de frascos e um de balas),
        sem flag de coleta, para poderem ser recebidos infinitas vezes.
  2. event/common.emevd.dcx
     -> adiciona um evento novo que executa AwardItemLot nesses dois lotes
        e o inicializa no evento 0 (que roda a cada carregamento de area).

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

BLOOD_VIAL_ID = 1000          # EquipParamGoods
QUICKSILVER_BULLET_ID = 900   # EquipParamGoods
GOODS_CATEGORY = 4            # ITEMLOT_ITEMCATEGORY: Good

ITEMLOT_PARAM_TYPE = "ITEMLOT_PARAM_ST"
ITEMLOT_ROW_SIZE = 148
# Lotes com IDs consecutivos sao entregues em cadeia; por isso usamos X e X+2
# e exigimos que X..X+3 estejam livres.
LOT_VIALS = 9990000
LOT_BULLETS = 9990002
RESTOCK_EVENT_ID = 9990000

GAMEPARAM_REL = ("param", "gameparam", "gameparam.parambnd.dcx")
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
# BND4
# ----------------------------------------------------------------------------

def _reverse_bits(b):
    return int("{:08b}".format(b)[::-1], 2)


def _read_cstr(data, off, unicode):
    if unicode:
        end = off
        while data[end:end + 2] != b"\0\0":
            end += 2
        return data[off:end].decode("utf-16-le")
    end = data.index(b"\0", off)
    return data[off:end].decode("shift_jis", errors="replace")


def bnd4_entries(data):
    if data[:4] != b"BND4":
        raise PatchError("Arquivo nao e BND4.")
    if data[9]:
        raise PatchError("BND4 big-endian nao suportado.")
    bit_big_endian = not data[10]
    count = struct.unpack_from("<i", data, 0x0C)[0]
    file_header_size = struct.unpack_from("<q", data, 0x20)[0]
    unicode = bool(data[0x30])
    raw_fmt = data[0x31]
    reverse = bit_big_endian or ((raw_fmt & 1) and not (raw_fmt & 0x80))
    fmt = raw_fmt if reverse else _reverse_bits(raw_fmt)
    has_ids, has_names = fmt & 0x02, fmt & 0x0C
    long_offsets, has_compression = fmt & 0x10, fmt & 0x20

    entries = []
    for i in range(count):
        p = 0x40 + i * file_header_size
        raw_flags = data[p]
        flags = raw_flags if bit_big_endian else _reverse_bits(raw_flags)
        e = {"compressed": bool(flags & 0x01), "csize_pos": p + 8}
        q = p + 16
        e["csize"] = struct.unpack_from("<q", data, p + 8)[0]
        e["usize_pos"] = None
        if has_compression:
            e["usize_pos"] = q
            q += 8
        e["offset_pos"], e["long_offset"] = q, bool(long_offsets)
        if long_offsets:
            e["offset"] = struct.unpack_from("<q", data, q)[0]
            q += 8
        else:
            e["offset"] = struct.unpack_from("<I", data, q)[0]
            q += 4
        if has_ids:
            q += 4
        e["name"] = ""
        if has_names:
            name_off = struct.unpack_from("<I", data, q)[0]
            e["name"] = _read_cstr(data, name_off, unicode)
        entries.append(e)
    return entries


def bnd4_find(data, basename):
    for e in bnd4_entries(data):
        if e["name"].replace("\\", "/").split("/")[-1].lower() == basename.lower():
            if e["compressed"]:
                raise PatchError("Arquivo %s comprimido dentro do BND4 (nao suportado)." % basename)
            return e
    raise PatchError("%s nao encontrado dentro do BND4." % basename)


def bnd4_replace(data, entry, new_bytes):
    """Anexa o novo conteudo no fim do BND4 e aponta o cabecalho para ele.
    Cabecalhos, nomes, tabela de hash e os demais arquivos ficam intactos."""
    out = bytearray(data)
    out += b"\0" * (-len(out) % 0x10)
    offset = len(out)
    out += new_bytes
    struct.pack_into("<q", out, entry["csize_pos"], len(new_bytes))
    if entry["usize_pos"] is not None:
        struct.pack_into("<q", out, entry["usize_pos"], len(new_bytes))
    if entry["long_offset"]:
        struct.pack_into("<q", out, entry["offset_pos"], offset)
    else:
        if offset > 0xFFFFFFFF:
            raise PatchError("BND4 grande demais.")
        struct.pack_into("<I", out, entry["offset_pos"], offset)
    return bytes(out)


def bnd4_get(data, entry):
    return data[entry["offset"]:entry["offset"] + entry["csize"]]


# ----------------------------------------------------------------------------
# PARAM
# ----------------------------------------------------------------------------

F2D_FLAG01, F2D_INT_DATA, F2D_LONG_DATA, F2D_OFFSET_TYPE = 0x01, 0x02, 0x04, 0x80


class Param:
    def __init__(self, data):
        self.data = data
        if data[0x2C] not in (0x00,):
            raise PatchError("PARAM big-endian nao suportado.")
        f2d = self.f2d = data[0x2D]
        self.f2e = data[0x2E]
        self.row_count = struct.unpack_from("<H", data, 0x0A)[0]
        self.short_data_start = not ((f2d & F2D_FLAG01 and f2d & F2D_INT_DATA) or f2d & F2D_LONG_DATA)
        self.long = bool(f2d & F2D_LONG_DATA)

        if f2d & F2D_OFFSET_TYPE:
            type_off = struct.unpack_from("<q", data, 0x10)[0]
            self.param_type = data[type_off:data.index(b"\0", type_off)].decode("ascii")
        else:
            self.param_type = data[0x0C:0x2C].split(b"\0")[0].split(b" ")[0].decode("ascii", "replace")

        if f2d & F2D_FLAG01 and f2d & F2D_INT_DATA:
            self.data_start_hdr = struct.unpack_from("<I", data, 0x30)[0]
            self.rows_start = 0x40
        elif self.long:
            self.data_start_hdr = struct.unpack_from("<q", data, 0x30)[0]
            self.rows_start = 0x40
        else:
            self.data_start_hdr = struct.unpack_from("<H", data, 0x04)[0]
            self.rows_start = 0x30

        if self.row_count < 2:
            raise PatchError("PARAM com poucas linhas; formato inesperado.")
        first_data = self._raw_data_offset(self.rows_start)
        named_size = 24 if self.long else 12
        self.named = (first_data - self.rows_start) >= self.row_count * named_size
        self.hdr_size = (24 if self.named else 16) if self.long else (12 if self.named else 8)
        if not self.short_data_start and self.rows_start + self.hdr_size > self.data_start_hdr:
            raise PatchError("PARAM sem cabecalhos de linha (nao suportado).")

        self.ids, self.offsets, self.names = [], [], []
        for i in range(self.row_count):
            p = self.rows_start + i * self.hdr_size
            self.ids.append(struct.unpack_from("<i", data, p)[0])
            if self.long:
                self.offsets.append(struct.unpack_from("<q", data, p + 8)[0])
                self.names.append(struct.unpack_from("<q", data, p + 16)[0] if self.named else None)
            else:
                self.offsets.append(struct.unpack_from("<I", data, p + 4)[0])
                self.names.append(struct.unpack_from("<I", data, p + 8)[0] if self.named else None)

        self.row_size = self.offsets[1] - self.offsets[0]
        for i, off in enumerate(self.offsets):
            if off != self.offsets[0] + i * self.row_size:
                raise PatchError("Dados do PARAM nao sao contiguos; formato inesperado.")
        for a, b in zip(self.ids, self.ids[1:]):
            if b < a:
                raise PatchError("IDs do PARAM fora de ordem; formato inesperado.")
        self.data_end = self.offsets[-1] + self.row_size

    def _raw_data_offset(self, p):
        if self.long:
            return struct.unpack_from("<q", self.data, p + 8)[0]
        return struct.unpack_from("<I", self.data, p + 4)[0]

    def row(self, row_id):
        i = self.ids.index(row_id)
        return self.data[self.offsets[i]:self.offsets[i] + self.row_size]

    def _empty_name_offset(self):
        unicode = bool(self.f2e & 0x01)
        terminator = b"\0\0" if unicode else b"\0"
        for off in self.names:
            if off and off < len(self.data) and self.data[off:off + len(terminator)] == terminator:
                return off
        return 0

    def with_rows(self, new_rows):
        """Retorna os bytes do PARAM com as linhas novas {id: bytes} inseridas."""
        rows = list(zip(self.ids, [self.data[o:o + self.row_size] for o in self.offsets], self.names))
        for rid, rbytes in new_rows.items():
            if rid in self.ids:
                raise PatchError("Linha %d ja existe em %s." % (rid, self.param_type))
            if len(rbytes) != self.row_size:
                raise PatchError("Tamanho de linha incorreto.")
        empty_name = self._empty_name_offset() if self.named else None
        added = len(new_rows)
        if self.row_count + added > 0xFFFF:
            raise PatchError("PARAM cheio.")
        for rid, rbytes in new_rows.items():
            rows.append((rid, rbytes, "NEW"))
        rows.sort(key=lambda r: r[0])

        hdr_growth = added * self.hdr_size
        tail_shift = hdr_growth + added * self.row_size
        old_hdr_end = self.rows_start + self.row_count * self.hdr_size
        gap = self.data[old_hdr_end:self.offsets[0]]
        tail = self.data[self.data_end:]
        new_data_start = self.offsets[0] + hdr_growth

        def shift_tail(off):
            if off is None:
                return None
            if off >= self.data_end:
                return off + tail_shift
            if off == 0:
                return 0
            raise PatchError("Offset de nome inesperado no PARAM.")

        new_empty = shift_tail(empty_name) if empty_name else 0

        head = bytearray(self.data[:self.rows_start])
        struct.pack_into("<H", head, 0x0A, len(rows))
        strings_off = struct.unpack_from("<I", head, 0)[0]
        if strings_off >= self.data_end:
            struct.pack_into("<I", head, 0, strings_off + tail_shift)
        if self.f2d & F2D_OFFSET_TYPE:
            type_off = struct.unpack_from("<q", head, 0x10)[0]
            struct.pack_into("<q", head, 0x10, shift_tail(type_off))
        if self.f2d & F2D_FLAG01 and self.f2d & F2D_INT_DATA:
            struct.pack_into("<I", head, 0x30, self.data_start_hdr + hdr_growth)
        elif self.long:
            struct.pack_into("<q", head, 0x30, self.data_start_hdr + hdr_growth)
        else:
            struct.pack_into("<H", head, 0x04, (self.data_start_hdr + hdr_growth) & 0xFFFF)

        headers = bytearray()
        body = bytearray()
        for j, (rid, rbytes, name) in enumerate(rows):
            data_off = new_data_start + j * self.row_size
            name_off = new_empty if name == "NEW" else shift_tail(name)
            if self.long:
                headers += struct.pack("<iiq", rid, 0, data_off)
                if self.named:
                    headers += struct.pack("<q", name_off)
            else:
                headers += struct.pack("<iI", rid, data_off)
                if self.named:
                    headers += struct.pack("<I", name_off)
            body += rbytes
        return bytes(head) + bytes(headers) + gap + bytes(body) + tail


def make_itemlot_row(item_id, quantity):
    if not 1 <= quantity <= 99:
        raise PatchError("Quantidade deve estar entre 1 e 99.")
    item_ids = [item_id] + [0] * 7
    categories = [GOODS_CATEGORY] + [0] * 7
    base_points = [1000] + [0] * 7          # 100% de chance no slot 1
    cumulate_points = [0] * 8
    slot_flags = [0] * 8                    # 0 = usa a flag principal
    get_item_flag = -1                      # <0 = sem flag: pode ser recebido sempre
    cumulate_flag = -1
    nums = [quantity] + [0] * 7
    bitfield = 0                            # enableLuck/cumulateReset desligados
    row = struct.pack("<8i8i8H8H8iiiBB8BH",
                      *item_ids, *categories, *base_points, *cumulate_points,
                      *slot_flags, get_item_flag, cumulate_flag, 0, 0, *nums, bitfield)
    assert len(row) == ITEMLOT_ROW_SIZE
    return row


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

def patch_gameparam(raw, vials, bullets):
    header, bnd = dcx_decompress(raw)
    entry = bnd4_find(bnd, "ItemLotParam.param")
    param = Param(bnd4_get(bnd, entry))
    if param.param_type != ITEMLOT_PARAM_TYPE:
        raise PatchError("ItemLotParam com tipo inesperado: %s" % param.param_type)
    if param.row_size != ITEMLOT_ROW_SIZE:
        raise PatchError("ItemLotParam com tamanho de linha %d (esperado %d). Versao do jogo diferente?"
                         % (param.row_size, ITEMLOT_ROW_SIZE))
    for rid in range(LOT_VIALS, LOT_VIALS + 4):
        if rid in param.ids:
            raise PatchError("Linha %d ja existe em ItemLotParam. Os arquivos ja foram modificados? "
                             "Use os arquivos originais do jogo." % rid)
    new_param = param.with_rows({
        LOT_VIALS: make_itemlot_row(BLOOD_VIAL_ID, vials),
        LOT_BULLETS: make_itemlot_row(QUICKSILVER_BULLET_ID, bullets),
    })

    # Verificacao: reler e comparar todas as linhas
    check = Param(new_param)
    for rid in param.ids:
        if check.row(rid) != param.row(rid):
            raise PatchError("Verificacao falhou: linha %d mudou." % rid)
    if check.row(LOT_VIALS) != make_itemlot_row(BLOOD_VIAL_ID, vials):
        raise PatchError("Verificacao falhou: linha nova incorreta.")
    if check.row_count != param.row_count + 2:
        raise PatchError("Verificacao falhou: contagem de linhas.")

    new_bnd = bnd4_replace(bnd, entry, new_param)
    if bnd4_get(new_bnd, bnd4_find(new_bnd, "ItemLotParam.param")) != new_param:
        raise PatchError("Verificacao falhou: BND4.")
    return dcx_compress(header, new_bnd)


def patch_common_emevd(raw):
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

    restock = Event(RESTOCK_EVENT_ID, rest=0)
    restock.instrs.append(Instr(2003, 4, struct.pack("<i", LOT_VIALS)))     # AwardItemLot
    restock.instrs.append(Instr(2003, 4, struct.pack("<i", LOT_BULLETS)))   # AwardItemLot
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
carregar o save) voce recebe {v} Blood Vials e {b} Quicksilver Bullets.
O que passar do limite do inventario vai para o Armazem.

Instalacao (em qualquer PC com a MESMA versao do jogo):
  1. Faca backup dos originais:
       dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx
       dvdroot_ps4/event/common.emevd.dcx
  2. Copie a pasta dvdroot_ps4 deste mod por cima da pasta dvdroot_ps4 do jogo
     (substituindo os dois arquivos).

Desinstalar: restaure os dois arquivos originais.
""".format(v=vials, b=bullets)
    with open(os.path.join(out_dir, "LEIA-ME.txt"), "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description="Gera o mod BB Restock para Bloodborne.")
    ap.add_argument("game_dir", help="Pasta do jogo (contem dvdroot_ps4) ou a propria dvdroot_ps4")
    ap.add_argument("--out", default="BB_Restock_Mod", help="Pasta de saida (padrao: BB_Restock_Mod)")
    ap.add_argument("--vials", type=int, default=20, help="Blood Vials por carregamento (1-99)")
    ap.add_argument("--bullets", type=int, default=20, help="Quicksilver Bullets por carregamento (1-99)")
    ap.add_argument("--install", action="store_true",
                    help="Tambem instala direto no jogo (cria .bak dos originais)")
    args = ap.parse_args()

    try:
        gp_path = find_file(args.game_dir, GAMEPARAM_REL)
        ev_path = find_file(args.game_dir, COMMON_EMEVD_REL)
        print("gameparam: %s" % gp_path)
        print("common.emevd: %s" % ev_path)

        with open(gp_path, "rb") as f:
            new_gp = patch_gameparam(f.read(), args.vials, args.bullets)
        print("ItemLotParam: lotes %d (frascos x%d) e %d (balas x%d) adicionados."
              % (LOT_VIALS, args.vials, LOT_BULLETS, args.bullets))
        with open(ev_path, "rb") as f:
            new_ev = patch_common_emevd(f.read())
        print("common.emevd: evento %d adicionado e inicializado no evento 0." % RESTOCK_EVENT_ID)

        outputs = [(gp_path, GAMEPARAM_REL, new_gp), (ev_path, COMMON_EMEVD_REL, new_ev)]
        for _src, rel, content in outputs:
            dst = os.path.join(args.out, "dvdroot_ps4", *rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(content)
        write_readme(args.out, args.vials, args.bullets)
        print("Mod gerado em: %s" % os.path.abspath(args.out))

        if args.install:
            for src, _rel, content in outputs:
                bak = src + ".bak"
                if not os.path.exists(bak):
                    shutil.copy2(src, bak)
                with open(src, "wb") as f:
                    f.write(content)
            print("Instalado no jogo (originais salvos como .bak).")
    except PatchError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
