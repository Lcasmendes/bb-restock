// Gera arquivos sinteticos no formato do Bloodborne com a SoulsFormats e
// verifica, tambem com a SoulsFormats, o resultado do bb_restock.py.
//   verify gen <dir> <variante 0-3>
//   verify verify <dir_original> <dir_mod> <vials> <bullets>
using SoulsFormats;


static class P
{
    static int Main(string[] a)
    {
        System.Text.Encoding.RegisterProvider(System.Text.CodePagesEncodingProvider.Instance);
        if (a[0] == "gen") Gen(a[1], int.Parse(a[2]));
        else return Verify(a[1], a[2], int.Parse(a[3]), int.Parse(a[4]));
        return 0;
    }

    static void Gen(string dir, int variant)
    {
        var evd = new EMEVD(EMEVD.Game.Bloodborne);
        var e0 = new EMEVD.Event(0, EMEVD.Event.RestBehaviorType.Default);
        for (int i = 0; i < 40; i++)
            e0.Instructions.Add(new EMEVD.Instruction(2000, 0, new object[] { i, (uint)(7000 + i), 0 }));
        e0.Instructions.Add(new EMEVD.Instruction(1000, 4, 1u, new object[] { (byte)1 }));
        e0.Parameters.Add(new EMEVD.Parameter(3, 8, 0, 4));
        evd.Events.Add(e0);
        evd.Events.Add(new EMEVD.Event(50, EMEVD.Event.RestBehaviorType.End));
        int n = 20 + 10 * variant;
        for (int k = 0; k < n; k++)
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
        Console.WriteLine($"gen ok variant {variant}: {evd.Events.Count} events");
    }

    static void Check(bool ok, string msg) { if (!ok) throw new Exception("FALHA: " + msg); }

    static byte[] Bytes(params object[] values)
    {
        var ms = new MemoryStream();
        var w = new BinaryWriter(ms);
        foreach (var v in values)
            switch (v)
            {
                case int i: w.Write(i); break;
                case uint u: w.Write(u); break;
                case byte b: w.Write(b); break;
                case sbyte s: w.Write(s); break;
                default: throw new ArgumentException(v.GetType().Name);
            }
        return ms.ToArray();
    }

    static void CheckTopUp(List<EMEVD.Instruction> ins, int start, int item, int max, int want, int held, sbyte group)
    {
        (int bank, int id, byte[] args)[] expected =
        {
            (2003, 41, Bytes(want, 8u, max, 0, 1u, (sbyte)5, (byte)0, (byte)0, (byte)0)),
            (2003, 42, Bytes(3, item, held, 8u)),
            (3, 12, Bytes(group, (byte)0, (byte)0, (byte)0, held, (byte)8, (byte)4, (byte)0, (byte)0, (uint)max)),
            (1000, 1, Bytes((byte)2, (byte)1, group, (byte)0)),
            (2003, 41, Bytes(want, 8u, 0, held, 8u, (sbyte)1, (byte)0, (byte)0, (byte)0)),
            (2003, 43, Bytes(3, item, want, 8u)),
        };
        for (int k = 0; k < expected.Length; k++)
        {
            var x = ins[start + k];
            Check(x.Bank == expected[k].bank && x.ID == expected[k].id && x.Layer == null, $"topup {item} instr {k}");
            Check(x.ArgData.SequenceEqual(expected[k].args), $"topup {item} args {k}");
        }
        Console.WriteLine($"  item {item}: completa ate {max}");
    }

    static int Verify(string orig, string mod, int vials, int bullets)
    {
        string gpRel = Path.Combine("dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx");
        string evRel = Path.Combine("dvdroot_ps4", "event", "common.emevd.dcx");
        Check(!File.Exists(Path.Combine(mod, gpRel)), "gameparam nao deve ser gerado");

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
        Check(ne.ID == 9990000 && ne.RestBehavior == EMEVD.Event.RestBehaviorType.Default, "new event");
        Check(ne.Instructions.Count == 12 && ne.Parameters.Count == 0, "new event size");
        CheckTopUp(ne.Instructions, 0, 1000, vials, 6960, 6970, 1);
        CheckTopUp(ne.Instructions, 6, 900, bullets, 6980, 6990, 2);
        Check(e1.StringData.SequenceEqual(e0.StringData) && e1.LinkedFileOffsets.SequenceEqual(e0.LinkedFileOffsets), "strings");
        // a regravacao pela SF deve ser identica ao que o patcher gerou
        var raw = DCX.Decompress(Path.Combine(mod, evRel));
        Check(e1.Write(new DCX.NoCompressionInfo()).SequenceEqual(raw), "SF rewrite identical");
        Console.WriteLine("VERIFY OK");
        return 0;
    }
}
