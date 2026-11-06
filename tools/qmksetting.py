# usage: qmksetting.py QSID [NEW_VALUE]   e.g. 7 = tapping term (ms), 8 = tap-hold flags (see README)
import sys
from _overlay import device
dev = device()
def get(q):
    r = dev.cmd(0xFE, 0x0A, q & 0xFF, q >> 8, match=False)
    return r[0], r[1] | r[2] << 8
q = int(sys.argv[1])
print(f"qsid {q} before:", get(q))
if len(sys.argv) > 2:
    v = int(sys.argv[2])
    dev.cmd(0xFE, 0x0B, q & 0xFF, q >> 8, v & 0xFF, v >> 8, match=False)
    print(f"qsid {q} after:", get(q))
dev.close()
