# Cheapino v2 QWERTY layout + live overlay

A beginner-friendly QWERTY, Miryoku-style layout for the
[Cheapino v2](https://github.com/tompi/cheapino) (36-key split, RP2040, one rotary encoder) running Vial,
plus a small always-on-top window that shows the active layer and the keys you're holding.

## Files

| Path | What it is |
|---|---|
| `vil.py` | Source of truth for the layout. `build` writes a Vial `.vil`, `show` prints it, `export` makes a numeric keymap for the overlay's `--write`. |
| `cheapino-qwerty.vil` | Generated layout. Load it in Vial: File > Load saved layout. |
| `template-tompi-miryoku.vil` | Official Cheapino Vial layout, used as the template (UID, tuned settings). |
| `keycodes_v6.json` | Keycode name -> number table, derived from vial-gui's `keycodes_v6.py`. |
| `overlay/cheapino_overlay.pyw` | Live layer overlay (Tk). Also `--test` and `--write keymap.json`. |
| `overlay/labels.json` | Key labels for the overlay. |
| `overlay/diag.py`, `brightness.py`, `qmksetting.py` | Small helpers: print board state, set LED brightness, get/set a QMK setting. |
| `overlay/50-cheapino.rules` | Linux udev rule so the overlay and Vial can open the keyboard without sudo. |
| `firmware/cheapino-layer-led.patch` | Optional firmware change: per-layer LED colour, LED keys that don't overwrite the base colour, and a raw-HID layer report the overlay uses. |

## Layout

Home-row mods (Shift on the pinkies), six layer-tap thumbs:

| Thumb (hold) | Layer |
|---|---|
| Esc | MEDIA (volume, track, screenshot, LED) |
| Space | NAV (arrows, home/end, undo/copy/paste) |
| Tab | MOUSE |
| Enter | SYM (`! @ # $ % ^ & * ( )`, braces, etc.) |
| Delete | FUN (F-keys) |
| Backspace | NUM (numpad, `1 2 3` on top) |

Knob scrolls and clicks Tab; on MEDIA it's volume and play/pause.
Run `python3 vil.py show cheapino-qwerty.vil` for the full grid.

## Changing the layout

```sh
# edit LAYERS in vil.py, then
python3 vil.py build template-tompi-miryoku.vil cheapino-qwerty.vil
```
Load the `.vil` in Vial, or push it without Vial (close Vial and the overlay first; two programs talking
raw HID at once steal each other's replies):
```sh
python3 vil.py export cheapino-qwerty.vil keymap.json
python3 overlay/cheapino_overlay.pyw --write keymap.json   # prints "verified: True"
```

Suggested tap-hold settings (Vial > QMK Settings, or `overlay/qmksetting.py`): tapping term 330 ms (qsid 7),
tap-hold flags 3 = permissive hold, no hold-on-other-key-press (qsid 8). This makes fast rolls type letters
instead of firing modifiers.

## Overlay

- **Windows:** no installs. `pythonw overlay/cheapino_overlay.pyw`
- **macOS:** `pip3 install hidapi`, then `python3 overlay/cheapino_overlay.pyw`. macOS may ask for Input Monitoring.
- **Linux:** `pip install hidapi`, install `overlay/50-cheapino.rules` (instructions inside), replug, run.

Drag to move, right-click for options. It pauses while Vial is open. With the stock firmware the layer is
guessed from held keys; with the patched firmware it's exact.

## Firmware (optional)

Applies to [tompi/vial-qmk](https://github.com/tompi/vial-qmk), branch `cheapinov2`, commit `9100f29`:
```sh
git clone -b cheapinov2 https://github.com/tompi/vial-qmk && cd vial-qmk
git checkout 9100f29 && git submodule update --init --recursive
git apply ../firmware/cheapino-layer-led.patch
make cheapino:vial          # needs gcc-arm-none-eabi and the qmk python requirements
```
Flash: hold the top-right key (Y) while plugging in, copy `cheapino_vial.uf2` to the RPI-RP2 drive.
The patched build enumerates as FEF3:AFB7. **Flashing resets the keymap and QMK settings**, so re-apply
both afterwards.

## Security notes

- The overlay only reads from the keyboard, except `--write`, which you run yourself. It uses fixed
  subprocess arguments (no shell) and only parses JSON.
- The upstream Cheapino firmware builds with `VIAL_INSECURE = yes`, so any program on your computer can
  change the keymap (including macros) without the physical unlock combo. Set it to `no` in
  `keyboards/cheapino/rules.mk` if that matters to you; Vial will then ask for the unlock combo, and
  `--write` will need the board unlocked first.

## Credits

Cheapino by tompi. Layer scheme after Miryoku by manna-harbour. Keycode table from vial-gui.

## Licence

GPL-2.0-or-later (see `LICENSE`), matching QMK and vial-gui, which parts of this are derived from.
