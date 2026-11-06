# Example: Cheapino v2 QWERTY layout

A beginner-friendly QWERTY, Miryoku-style layout for the [Cheapino v2](https://github.com/tompi/cheapino)
(36-key split, RP2040, one rotary encoder).

| File | What it is |
|---|---|
| `vil.py` | The layout source. `build` writes a Vial `.vil`, `show` prints it, `export` makes a numeric keymap for `vial_overlay.pyw --write`. |
| `cheapino-qwerty.vil` | Generated layout. Load it in Vial: File > Load saved layout. |
| `template-tompi-miryoku.vil` | Official Cheapino Vial layout, used as the template (UID, tuned settings). |
| `keycodes_v6.json` | Keycode name to number table, derived from vial-gui's `keycodes_v6.py`. |
| `config.json` | Overlay settings for this layout (layer names and colours). Copy it next to `vial_overlay.pyw`. |
| `firmware/cheapino-layer-led.patch` | Per-layer LED colour, LED keys that don't overwrite the base colour, and the overlay's layer report. |

## Layout

Home-row mods (Shift on the pinkies) and six layer-tap thumbs:

| Thumb (hold) | Layer |
|---|---|
| Esc | MEDIA (volume, track, LED brightness and on/off) |
| Space | NAV (arrows, Home/End, undo/copy/paste) |
| Tab | MOUSE |
| Enter | SYM (`! @ # $ % ^ & * ( )`, braces, etc.) |
| Delete | FUN (F-keys) |
| Backspace | NUM (numpad, `1 2 3` on top) |

The knob scrolls and clicks Tab. On MEDIA it changes volume and plays/pauses.
Run `python3 vil.py show cheapino-qwerty.vil` for the full grid.

## Changing it

```sh
# edit LAYERS in vil.py, then
python3 vil.py build template-tompi-miryoku.vil cheapino-qwerty.vil
python3 vil.py export cheapino-qwerty.vil keymap.json
python3 ../../vial_overlay.pyw --write keymap.json     # or load the .vil in Vial
```

Suggested tap-hold settings (Vial > QMK Settings, or `tools/qmksetting.py`):

- tapping term 330 ms (qsid 7)
- tap-hold flags 3 = permissive hold, no hold-on-other-key-press (qsid 8)

With these, fast rolls type letters instead of firing modifiers.

## Firmware (optional)

For [tompi/vial-qmk](https://github.com/tompi/vial-qmk), branch `cheapinov2`, commit `9100f29`:
```sh
git clone -b cheapinov2 https://github.com/tompi/vial-qmk && cd vial-qmk
git checkout 9100f29 && git submodule update --init --recursive
git apply /path/to/firmware/cheapino-layer-led.patch
make cheapino:vial          # needs gcc-arm-none-eabi and the qmk python requirements
```
To flash, hold Y while plugging in, then copy `cheapino_vial.uf2` to the RPI-RP2 drive. The patched build
enumerates as FEF3:AFB7.

**Flashing resets the keymap and QMK settings**, so re-apply both afterwards.

Upstream builds with `VIAL_INSECURE = yes`, which means any program on the computer can change the keymap
without the unlock combo. Set it to `no` in `keyboards/cheapino/rules.mk` if that matters to you.

Credits: Cheapino by tompi. Layer scheme after Miryoku by manna-harbour.
