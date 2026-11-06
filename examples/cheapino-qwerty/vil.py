#!/usr/bin/env python3
"""Cheapino v2 Vial layout helper.

  python3 vil.py show  FILE.vil          # print every non-empty layer as a grid
  python3 vil.py build TEMPLATE.vil OUT  # write the QWERTY Miryoku-style layout below into OUT
  python3 vil.py export FILE.vil OUT.json # numeric keymap for `vial_overlay.pyw --write OUT.json`

Physical -> matrix mapping comes from tompi/vial-qmk (cheapinov2) info.json.
"""
import json, sys

LEFT  = [[(4,10),(4,9),(4,8),(4,7),(4,6)], [(5,10),(5,9),(5,8),(5,7),(5,6)], [(6,10),(6,9),(6,8),(6,7),(6,6)]]
RIGHT = [[(0,0),(0,1),(0,2),(0,3),(0,4)],  [(1,0),(1,1),(1,2),(1,3),(1,4)],  [(2,0),(2,1),(2,2),(2,3),(2,4)]]
THUMBS = [(6,11),(5,11),(4,11), (0,5),(1,5),(2,5)]   # left outer->inner, right inner->outer
ENC_PRESS = (3,0)
NAMES = ["BASE","NAV","MOUSE","MEDIA","NUM","SYM","FUN"]

X = "KC_NO"; T = "KC_TRNS"
LMODS = ["KC_LSHIFT","KC_LALT","KC_LCTRL",X,X]      # mods held on the inactive hand (same spots as base)
RMODS = [X,X,"KC_LCTRL","KC_LALT","KC_LSHIFT"]
LBOT = ["KC_LGUI",X,X,X,X]
RBOT = [X,X,X,X,"KC_LGUI"]
NONE5 = [X]*5
UNDO_ROW = ["LCTL(KC_Y)","LCTL(KC_V)","LCTL(KC_C)","LCTL(KC_X)","LCTL(KC_Z)"]  # redo paste copy cut undo (Windows)

# each layer: (left 3 rows, right 3 rows, 6 thumbs)
LAYERS = [
  # 0 BASE - QWERTY with home-row mods (GUI/Alt/Ctrl/Shift), Miryoku thumbs
  ([["KC_Q","KC_W","KC_E","KC_R","KC_T"],
    ["LSFT_T(KC_A)","LALT_T(KC_S)","LCTL_T(KC_D)","KC_F","KC_G"],
    ["LGUI_T(KC_Z)","KC_X","KC_C","KC_V","KC_B"]],
   [["KC_Y","KC_U","KC_I","KC_O","KC_P"],
    ["KC_H","KC_J","LCTL_T(KC_K)","LALT_T(KC_L)","LSFT_T(KC_QUOTE)"],
    ["KC_N","KC_M","KC_COMMA","KC_DOT","LGUI_T(KC_SLASH)"]],
   ["LT3(KC_ESCAPE)","LT1(KC_SPACE)","LT2(KC_TAB)","LT5(KC_ENTER)","LT6(KC_DELETE)","LT4(KC_BSPACE)"]),
  # 1 NAV (hold Space)
  ([NONE5, LMODS, LBOT],
   [UNDO_ROW,
    ["KC_CAPSLOCK","KC_LEFT","KC_DOWN","KC_UP","KC_RIGHT"],
    ["KC_INSERT","KC_HOME","KC_PGDOWN","KC_PGUP","KC_END"]],
   [X,T,X,"KC_ENTER","KC_DELETE","KC_BSPACE"]),
  # 2 MOUSE (hold Tab)
  ([NONE5, LMODS, LBOT],
   [UNDO_ROW,
    [X,"KC_MS_L","KC_MS_D","KC_MS_U","KC_MS_R"],
    [X,"KC_WH_L","KC_WH_D","KC_WH_U","KC_WH_R"]],
   [X,X,T,"KC_BTN2","KC_BTN1","KC_BTN3"]),
  # 3 MEDIA (hold Esc)
  ([NONE5, LMODS, LBOT],
   [["LSG(KC_S)",X,"RGB_VAD","RGB_VAI","RGB_TOG"],   # screenshot, -, LED dimmer, LED brighter, LED on/off
    [X,"KC_MPRV","KC_VOLD","KC_VOLU","KC_MNXT"],
    NONE5],
   [T,X,X,"KC_MSTP","KC_MPLY","KC_MUTE"]),
  # 4 NUM (hold Backspace)
  ([["KC_LBRACKET","KC_1","KC_2","KC_3","KC_RBRACKET"],
    ["KC_SCOLON","KC_4","KC_5","KC_6","KC_EQUAL"],
    ["KC_GRAVE","KC_7","KC_8","KC_9","KC_BSLASH"]],
   [NONE5, RMODS, RBOT],
   ["KC_DOT","KC_0","KC_MINUS",X,X,T]),
  # 5 SYM (hold Enter)
  ([["KC_EXLM","KC_AT","KC_HASH","KC_DLR","KC_PERC"],      # classic Shift+1..5
    ["KC_LCBR","KC_RCBR","KC_COLN","KC_PLUS","KC_PIPE"],
    ["KC_TILD","KC_MINUS","KC_DQUO","KC_LT","KC_GT"]],
   [["KC_CIRC","KC_AMPR","KC_ASTR","KC_LPRN","KC_RPRN"],     # classic Shift+6..0
    RMODS, RBOT],
   ["KC_LBRACKET","KC_RBRACKET","KC_UNDS",T,X,X]),
  # 6 FUN (hold Delete)
  ([["KC_F12","KC_F7","KC_F8","KC_F9","KC_PSCREEN"],
    ["KC_F11","KC_F4","KC_F5","KC_F6","KC_SCROLLLOCK"],
    ["KC_F10","KC_F1","KC_F2","KC_F3","KC_PAUSE"]],
   [NONE5, RMODS, RBOT],
   ["KC_APPLICATION","KC_SPACE","KC_TAB",X,T,X]),
]
ENCODER = [["KC_WH_U","KC_WH_D"]] * len(LAYERS)   # [one direction, other direction] per layer: scroll
ENCODER[3] = ["KC_VOLD","KC_VOLU"]                # MEDIA (hold Esc): volume
ENC_PRESS_KEYS = ["KC_TAB"] * len(LAYERS)          # click = Tab
ENC_PRESS_KEYS[3] = "KC_MPLY"                      # MEDIA: click = play/pause

def show(path):
    d = json.load(open(path))
    for i, l in enumerate(d["layout"]):
        keys = [l[r][c] for row in LEFT+RIGHT for r,c in row] + [l[r][c] for r,c in THUMBS]
        if all(k in ("KC_NO","KC_TRNS",-1) for k in keys):
            continue
        print(f"--- layer {i} {NAMES[i] if i < len(NAMES) else ''}")
        for a, b in zip(LEFT, RIGHT):
            print(" ".join(f"{str(l[r][c]):>15}" for r,c in a), " | ", " ".join(f"{str(l[r][c]):>15}" for r,c in b))
        print("thumbs:", [l[r][c] for r,c in THUMBS], " encoder press:", l[ENC_PRESS[0]][ENC_PRESS[1]],
              " encoder turn:", d["encoder_layout"][i][0])

def build(template, out):
    d = json.load(open(template))
    for i in range(len(d["layout"])):
        layer = d["layout"][i]
        if i < len(LAYERS):
            left, right, thumbs = LAYERS[i]
            for rows, coords in ((left, LEFT), (right, RIGHT)):
                for keys, pos in zip(rows, coords):
                    for k, (r,c) in zip(keys, pos):
                        layer[r][c] = k
            for k, (r,c) in zip(thumbs, THUMBS):
                layer[r][c] = k
            layer[ENC_PRESS[0]][ENC_PRESS[1]] = ENC_PRESS_KEYS[i]
            d["encoder_layout"][i] = [list(ENCODER[i])]
        else:  # unused layers 7-13: blank
            for row in LEFT+RIGHT:
                for r,c in row: layer[r][c] = X
            for r,c in THUMBS: layer[r][c] = X
            layer[ENC_PRESS[0]][ENC_PRESS[1]] = X
            d["encoder_layout"][i] = [["KC_NO","KC_NO"]]
    with open(out, "w", newline="\n") as f:
        json.dump(d, f)

def encode(name, table):
    if isinstance(name, int): return name
    if name in table: return table[name]
    import re
    m = re.fullmatch(r"([A-Z0-9_]+)\((KC_[A-Z0-9_]+)\)", name)
    if m and m.group(1) + "(kc)" in table and m.group(2) in table:
        return table[m.group(1) + "(kc)"] | table[m.group(2)]
    raise ValueError(f"unknown keycode {name!r}")

def export(path, out):
    import os
    table = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "keycodes_v6.json")))
    d = json.load(open(path))
    keymap = [[[encode(k, table) if k != -1 else 0 for k in row] for row in layer] for layer in d["layout"]]
    enc = [[[encode(a, table), encode(b, table)] for a, b in layer] for layer in d["encoder_layout"]]
    json.dump({"keymap": keymap, "encoders": enc}, open(out, "w"))
    print(f"exported {len(keymap)} layers, {sum(len(r) for l in keymap for r in l)} keys")

if __name__ == "__main__":
    if sys.argv[1] == "show": show(sys.argv[2])
    elif sys.argv[1] == "build": build(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "export": export(sys.argv[2], sys.argv[3])
