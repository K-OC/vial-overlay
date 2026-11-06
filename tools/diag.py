# usage: diag.py   - print what the keyboard reports (name, layers, layer report, QMK RGB Light values)
from _overlay import ov
dev, b = ov.connect()
print(f"{b.name}: {b.layers} layers, {b.rows}x{b.cols} matrix, {len(b.visible)} keys, {b.n_enc} encoders")
print("firmware layer report:", b.fw_layer, " layer now:", dev.cmd(0x40)[1] if b.fw_layer else "-")
if b.definition.get("lighting") in ("qmk_rgblight", "qmk_backlight_rgblight"):
    for name, vid in (("brightness", 0x80), ("effect", 0x81), ("color (hue, sat)", 0x83)):
        print(f"rgblight {name}:", list(dev.cmd(0x08, vid)[2:4]))
for l in range(min(b.layers, 4)):
    print(f"{ov.layer_name(l)} knobs:", [tuple(ov.label(x)[0].replace("\n", " ") for x in e) for e in b.encoders[l]])
dev.close()
