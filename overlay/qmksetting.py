# usage: qmksetting.py QSID [NEW_VALUE]   (7 = tapping term ms, 8 = tap-hold flags)
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ov", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "cheapino_overlay.pyw"))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)
dev = ov.RawHid(ov.RawHid.find())
def get(q):
    r = dev.cmd(0xFE, 0x0A, q & 0xFF, q >> 8, match=False)
    return r[0], r[1] | r[2] << 8
for q in map(int, sys.argv[1].split(",")):
    print(f"qsid {q} before:", get(q))
if len(sys.argv) > 2:
    q, v = int(sys.argv[1]), int(sys.argv[2])
    r = dev.cmd(0xFE, 0x0B, q & 0xFF, q >> 8, v & 0xFF, v >> 8, match=False)
    print(f"qsid {q} after:", get(q))
dev.close()
