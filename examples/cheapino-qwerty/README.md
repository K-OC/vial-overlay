# Cheapino v2 QWERTY

A beginner-friendly QWERTY, Miryoku-style layout for the [Cheapino v2](https://github.com/tompi/cheapino).
Shift and the other modifiers are on the home row; the thumbs switch layers when held:

| Hold | Layer |
|---|---|
| Esc | Media, LED |
| Space | Arrows, undo/copy/paste |
| Tab | Mouse |
| Enter | Symbols |
| Delete | F-keys |
| Backspace | Numbers |

On the base layer, turning the knob moves with Tab / Shift+Tab and clicking it is a mouse click. On other layers it scrolls.

## Use it

Load `cheapino-qwerty.vil` in Vial (File > Load saved layout). Copy `config.json` next to
`vial_overlay.pyw` to get layer names and colours.

To change the layout, edit `vil.py` and run:
```sh
python3 vil.py build template-tompi-miryoku.vil cheapino-qwerty.vil
```

Recommended tap-hold settings (Vial > QMK Settings):

- Tapping term 330 ms
- Permissive hold on
- Hold on other key press off

With these, fast typing doesn't trigger modifiers by accident.

## Firmware (optional)

`firmware/cheapino-layer-led.patch` adds per-layer LED colours and the overlay's layer report. Apply it to
[tompi/vial-qmk](https://github.com/tompi/vial-qmk) (branch `cheapinov2`, commit `9100f29`) and build
with `make cheapino:vial`. Flashing resets your keymap and settings, so reload them afterwards.
