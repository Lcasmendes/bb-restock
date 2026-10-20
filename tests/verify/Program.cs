// Gera arquivos sinteticos no formato do Bloodborne com a SoulsFormats e
// verifica, tambem com a SoulsFormats, o resultado do bb_restock.py.
//   verify gen <dir> <variante 0-3>
//   verify verify <dir_original> <dir_mod> <vials> <bullets>
using SoulsFormats;


static class P
{
    static string DefPath = Environment.GetEnvironmentVariable("BB_ITEMLOT_DEF")
        ?? throw new Exception("Defina BB_ITEMLOT_DEF com o caminho de ItemLotParam.xml (Smithbox, BB).");

    static int Main(string[] a)
    {
        System.Text.Encoding.RegisterProvider(System.Text.CodePagesEncodingProvider.Instance);
        if (a[0] == "gen") Gen(a[1], int.Parse(a[2]));
        else return Verify(a[1], a[2], int.Parse(a[3]), int.Parse(a[4]));
        return 0;
    }

    static PARAM MakeParam(int variant, PARAMDEF def)
    {
        var p = new PARAM();
        typeof(PARAM).GetProperty("AppliedParamdef").SetValue(p, def);
        p.ParamType = "ITEMLOT_PARAM_ST";
        p.ParamdefDataVersion = 2; p.Unk06 = 0;
        p.Format2D = variant switch { 0 => 0, 1 => (PARAM.FormatFlags1)0x03, 2 => (PARAM.FormatFlags1)0x05, _ => (PARAM.FormatFlags1)0x85 };
        p.Format2E = variant % 2 == 0 ? (PARAM.FormatFlags2)0 : (PARAM.FormatFlags2)1;
        p.ParamdefFormatVersion = 3;
        p.Rows = new List<PARAM.Row>();
        var rnd = new Random(variant);
        int id = 1000;
        int n = variant == 0 ? 3000 : 9700;
        for (int i = 0; i < n; i++)
        {
            id += rnd.Next(1, 3000);
            if (id >= 9990000 && id <= 9990003) id = 9990010;
            var r = new PARAM.Row(id, i % 7 == 0 ? "" : $"Lote {i} ação", def);
            foreach (var c in r.Cells)
            {
                var t = c.Value.GetType();
                if (t == typeof(int)) c.Value = rnd.Next(-1, 100000);
                else if (t == typeof(ushort)) c.Value = (ushort)rnd.Next(0, 1000);
                else if (t == typeof(byte)) c.Value = (byte)rnd.Next(0, 2);
            }
            p.Rows.Add(r);
        }
        return p;
    }

    static void Gen(string dir, int variant)
    {
        var def = PARAMDEF.XmlDeserialize(DefPath);
        var param = MakeParam(variant, def);
        var bnd = new BND4
        {
            Format = variant % 2 == 0 ? (Binder.Format)0x74 : (Binder.Format)0x3E,
            Unicode = true, Extended = (byte)(variant % 2 == 0 ? 4 : 0), BigEndian = false, BitBigEndian = false, Version = "16G12P17"
        };
        var rnd = new Random(99 + variant);
        string[] names = { "AtkParam_Npc.param", "EquipParamGoods.param", "ItemLotParam.param", "NpcParam.param", "SpEffectParam.param" };
        for (int i = 0; i < names.Length; i++)
        {
            byte[] bytes;
            if (names[i] == "ItemLotParam.param") bytes = param.Write();
            else { bytes = new byte[rnd.Next(1000, 50000)]; rnd.NextBytes(bytes); }
            bnd.Files.Add(new BinderFile(Binder.FileFlags.Flag1, i, @"N:\SPRJ\data\Param\param\GameParam\" + names[i], bytes));
        }
        var gp = Path.Combine(dir, "dvdroot_ps4", "param", "gameparam");
        Directory.CreateDirectory(gp);
        File.WriteAllBytes(Path.Combine(gp, "gameparam.parambnd.dcx"), bnd.Write(new DCX.DcxDfltCompressionInfo(DCX.DfltCompressionPreset.DCX_DFLT_10000_44_9)));

        var evd = new EMEVD(EMEVD.Game.Bloodborne);
        var e0 = new EMEVD.Event(0, EMEVD.Event.RestBehaviorType.Default);
        for (int i = 0; i < 40; i++)
            e0.Instructions.Add(new EMEVD.Instruction(2000, 0, new object[] { i, (uint)(7000 + i), 0 }));
        e0.Instructions.Add(new EMEVD.Instruction(1000, 4, 1u, new object[] { (byte)1 }));
        e0.Parameters.Add(new EMEVD.Parameter(3, 8, 0, 4));
        evd.Events.Add(e0);
        evd.Events.Add(new EMEVD.Event(50, EMEVD.Event.RestBehaviorType.End));
        for (int k = 0; k < 40; k++)
        {
            var ev = new EMEVD.Event(7000 + k, (EMEVD.Event.RestBehaviorType)(k % 3));
            for (int j = 0; j < 1 + k % 5; j++)
                ev.Instructions.Add(j % 3 == 2 ? new EMEVD.Instruction(2003, 4, (uint)(1 << (k % 4)), new object[] { 1000 * k + j })
                                               : new EMEVD.Instruction(3, 0, new object[] { (sbyte)0, (byte)1, (byte)0, 1000 + k, (short)j }));
            if (k % 2 == 1) ev.Parameters.Add(new EMEVD.Parameter(0, 4, 0, 4));
            evd.Events.Add(ev);
        }
        evd.StringData = System.Text.Encoding.Unicode.GetBytes("\0m29_00_00_00\0\0");
        evd.LinkedFileOffsets = new List<long> { 2 };
        var evdir = Path.Combine(dir, "dvdroot_ps4", "event");
        Directory.CreateDirectory(evdir);
        File.WriteAllBytes(Path.Combine(evdir, "common.emevd.dcx"), evd.Write(new DCX.DcxDfltCompressionInfo(DCX.DfltCompressionPreset.DCX_DFLT_10000_44_9)));
        Console.WriteLine($"gen ok variant {variant}: {param.Rows.Count} rows, 2D=0x{(byte)param.Format2D:X2}, bnd fmt=0x{(byte)bnd.Format:X2}");
    }

    static void Check(bool ok, string msg) { if (!ok) throw new Exception("FALHA: " + msg); }

    static int Verify(string orig, string mod, int vials, int bullets)
    {
        var def = PARAMDEF.XmlDeserialize(DefPath);
        string gpRel = Path.Combine("dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx");
        string evRel = Path.Combine("dvdroot_ps4", "event", "common.emevd.dcx");
        var b0 = BND4.Read(Path.Combine(orig, gpRel));
        var b1 = BND4.Read(Path.Combine(mod, gpRel));
        Check(b0.Files.Count == b1.Files.Count, "file count");
        PARAM p0 = null, p1 = null;
        for (int i = 0; i < b0.Files.Count; i++)
        {
            Check(b0.Files[i].Name == b1.Files[i].Name && b0.Files[i].ID == b1.Files[i].ID, "names/ids");
            if (b0.Files[i].Name.EndsWith("ItemLotParam.param")) { p0 = PARAM.Read(b0.Files[i].Bytes); p1 = PARAM.Read(b1.Files[i].Bytes); }
            else Check(b0.Files[i].Bytes.SequenceEqual(b1.Files[i].Bytes), "other file changed");
        }
        p0.ApplyParamdef(def); p1.ApplyParamdef(def);
        Check(p1.Rows.Count == p0.Rows.Count + 2, "row count");
        var map = p1.Rows.ToDictionary(r => r.ID);
        foreach (var r in p0.Rows)
        {
            var r1 = map[r.ID];
            Check(r.Name == r1.Name, $"name {r.ID} '{r.Name}' vs '{r1.Name}'");
            for (int c = 0; c < r.Cells.Count; c++) Check(Equals(r.Cells[c].Value, r1.Cells[c].Value), $"cell {r.ID}");
        }
        for (int i = 1; i < p1.Rows.Count; i++) Check(p1.Rows[i].ID > p1.Rows[i - 1].ID, "sorted");
        void CheckLot(int id, int item, int num)
        {
            var r = map[id];
            Check((int)r["lotItemId01"].Value == item, "item");
            Check((int)r["lotItemCategory01"].Value == 4, "cat");
            Check((ushort)r["lotItemBasePoint01"].Value == 1000, "points");
            Check((byte)r["lotItemNum01"].Value == num, "num");
            Check((int)r["getItemFlagId"].Value == -1, "flag");
            Check((int)r["cumulateNumFlagId"].Value == -1, "cflag");
            for (int k = 2; k <= 8; k++) Check((ushort)r[$"lotItemBasePoint0{k}"].Value == 0, "other points");
            Console.WriteLine($"  lote {id}: item {item} x{num} nome='{r.Name}'");
        }
        CheckLot(9990000, 1000, vials); CheckLot(9990002, 900, bullets);
        Check(!map.ContainsKey(9990001) && !map.ContainsKey(9990003), "chain ids free");
        // SF consegue regravar o param modificado
        PARAM.Read(p1.Write());

        var e0 = EMEVD.Read(Path.Combine(orig, evRel));
        var e1 = EMEVD.Read(Path.Combine(mod, evRel));
        Check(e1.Events.Count == e0.Events.Count + 1, "event count");
        for (int i = 0; i < e0.Events.Count; i++)
        {
            var a = e0.Events[i]; var b = e1.Events[i];
            Check(a.ID == b.ID && a.RestBehavior == b.RestBehavior, "event hdr");
            int off = a.ID == 0 ? 1 : 0;
            Check(b.Instructions.Count == a.Instructions.Count + off, "instr count");
            for (int j = 0; j < a.Instructions.Count; j++)
            {
                var x = a.Instructions[j]; var y = b.Instructions[j + off];
                Check(x.Bank == y.Bank && x.ID == y.ID && x.Layer == y.Layer && x.ArgData.SequenceEqual(y.ArgData), "instr");
            }
            Check(a.Parameters.Count == b.Parameters.Count, "params");
            for (int j = 0; j < a.Parameters.Count; j++)
            {
                var x = a.Parameters[j]; var y = b.Parameters[j];
                Check(x.InstructionIndex + off == y.InstructionIndex && x.TargetStartByte == y.TargetStartByte && x.SourceStartByte == y.SourceStartByte && x.ByteCount == y.ByteCount, "param");
            }
        }
        var init = e1.Events.First(e => e.ID == 0).Instructions[0];
        Check(init.Bank == 2000 && init.ID == 0 && init.ArgData.SequenceEqual(new byte[] { 0,0,0,0, 0x70,0x6F,0x98,0, 0,0,0,0 }), "init instr");
        var ne = e1.Events.Last();
        Check(ne.ID == 9990000 && ne.Instructions.Count == 2 && ne.Parameters.Count == 0, "new event");
        Check(ne.Instructions.All(x => x.Bank == 2003 && x.ID == 4 && x.Layer == null), "award instr");
        Check(BitConverter.ToInt32(ne.Instructions[0].ArgData) == 9990000 && BitConverter.ToInt32(ne.Instructions[1].ArgData) == 9990002, "award args");
        Check(e1.StringData.SequenceEqual(e0.StringData) && e1.LinkedFileOffsets.SequenceEqual(e0.LinkedFileOffsets), "strings");
        // a regravacao pela SF deve ser identica ao que o patcher gerou
        var raw = DCX.Decompress(Path.Combine(mod, evRel));
        Check(e1.Write(new DCX.NoCompressionInfo()).SequenceEqual(raw), "SF rewrite identical");
        Console.WriteLine("VERIFY OK");
        return 0;
    }
}
