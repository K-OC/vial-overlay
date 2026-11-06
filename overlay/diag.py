import importlib.util, sys
sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("ov", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "cheapino_overlay.pyw"))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)
dev = ov.RawHid(ov.RawHid.find()); b = ov.Board(dev)
print("fw layer report:", b.fw_layer, " layer now:", dev.cmd(0x40)[1] if b.fw_layer else "-")
print("base thumbs:", [ov.label(b.keymap[0][r][c])[0] for r, c in ov.THUMBS])
print("base home row:", [ov.label(b.keymap[0][r][c])[0] for r, c in ov.LEFT[1]])
for name, vid in (("brightness", 0x80), ("effect", 0x81), ("color(hue,sat)", 0x83)):
    r = dev.cmd(0x08, vid); print(f"rgblight {name}:", list(r[:5]))
dev.close()
dev = ov.RawHid(ov.RawHid.find()); b = ov.Board(dev)
for l in range(3):
    print(f"layer {l} knob:", [ov.label(x)[0].replace("\n", " ") for x in b.encoders[l]], " click:", ov.label(b.keymap[l][3][0])[0].replace("\n", " "))
dev.close()
