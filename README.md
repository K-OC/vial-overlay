# vial-overlay

A small always-on-top window that shows which layer your keyboard is on and which keys you're holding.
Works with any keyboard running [Vial](https://get.vial.today), on Windows, macOS and Linux.

It reads everything from the keyboard: the board's shape, every layer, and the knobs. There's nothing to
set up per keyboard.

## Run it

You need Python 3 with Tkinter (the python.org installer includes it).

- **Windows:** `pythonw vial_overlay.pyw`
- **macOS:** `pip3 install hidapi`, then `python3 vial_overlay.pyw`
- **Linux:** `pip install hidapi`, install `linux/50-vial.rules` (instructions inside), then
  `python3 vial_overlay.pyw`

Drag the window to move it. Right-click for options. It pauses while Vial is open.
`--test` prints what it reads, without opening a window.

## Settings

Optional. Copy `config.example.json` to `config.json` to name your layers and pick their colours.

## Layer detection

Stock Vial firmware doesn't say which layer is active, so the overlay works it out from the keys you're
holding. That works for hold-to-switch layers (`LT`, `MO`, `TT`) but not toggled ones. For exact detection,
add this to your firmware and set `"firmware_layer_report": true`:

```c
void raw_hid_receive_kb(uint8_t *data, uint8_t length) {
    if (data[0] == 0x40) {
        layer_state_t st = layer_state | default_layer_state;
        data[1] = get_highest_layer(st);
        data[2] = st; data[3] = st >> 8; data[4] = st >> 16; data[5] = st >> 24;
    } else {
        data[0] = 0xFF;
    }
}
```

Highlighting held keys uses Vial's matrix tester. If your firmware isn't built with `VIAL_INSECURE`, unlock
the board in Vial first.

## Also included

- `tools/`: print board info, set LED brightness, change QMK settings
- `--write keymap.json`: push a keymap without opening Vial
- `examples/cheapino-qwerty/`: a full Cheapino v2 setup (layout, overlay config, firmware patch)

The overlay only reads from your keyboard; `--write` is the only thing that changes it.

## License

GPL-2.0-or-later. Key labels come from [vial-gui](https://github.com/vial-kb/vial-gui), which is GPL too.
