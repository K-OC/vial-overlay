# usage: brightness.py VALUE   (0-255; keyboards using QMK RGB Light)
import sys
from _overlay import device
dev = device()
dev.cmd(0x07, 0x80, int(sys.argv[1]), match=False); dev.cmd(0x09, match=False)   # set + save
print("brightness now:", dev.cmd(0x08, 0x80)[2]); dev.close()
