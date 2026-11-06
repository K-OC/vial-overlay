import importlib.util, sys
spec = importlib.util.spec_from_file_location("ov", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "cheapino_overlay.pyw"))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)
val = int(sys.argv[1])
dev = ov.RawHid(ov.RawHid.find())
dev.cmd(0x07, 0x80, val, match=False); dev.cmd(0x09, match=False)
print("brightness now:", dev.cmd(0x08, 0x80)[2]); dev.close()
