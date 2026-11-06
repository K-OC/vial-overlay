"""Cheapino v2 live keymap overlay (Windows, macOS, Linux; Vial firmware).

Always-on-top window that shows the layer you are on and highlights held keys.
Reads the keymap straight from the keyboard, so it stays correct after Vial edits
(right-click -> Reload keymap).

Layer detection:
  * custom firmware (reports layer via raw HID 0x40) -> exact
  * stock Vial firmware -> worked out from which layer keys are physically held

Right-click the window for options. Drag it with the left mouse button.
Pauses itself while Vial is open (both talking to the keyboard at once confuses Vial).

Windows: works as is (no installs).  macOS / Linux: pip install hidapi
Linux also needs a udev rule so you can open the keyboard without sudo (see 50-cheapino.rules).

Run:  pythonw cheapino_overlay.pyw        (no console window; on Mac/Linux: python3 cheapino_overlay.pyw &)
Test: python  cheapino_overlay.pyw --test (prints what it reads, no window)
Write: python cheapino_overlay.pyw --write keymap.json (push a keymap exported by vil.py; close Vial first)
"""
import ctypes, ctypes.wintypes as wt, json, os, subprocess, sys, threading, time

VIDPIDS = [(0xFEE3, 0x0000), (0xFEF3, 0xAFB7)]  # release Vial build, custom build
IDS = [f"vid_{v:04x}&pid_{p:04x}" for v, p in VIDPIDS]
WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
FONT = "Segoe UI" if WIN else ("Helvetica Neue" if MAC else "DejaVu Sans")
RAW_USAGE_PAGE = 0xFF60

LAYER_NAMES  = ["BASE", "NAV", "MOUSE", "MEDIA", "NUM", "SYM", "FUN"]
LAYER_HOLD   = {1: "hold Space", 2: "hold Tab", 3: "hold Esc", 4: "hold Backspace", 5: "hold Enter", 6: "hold Delete"}
LAYER_COLORS = ["#4a5060", "#2f6fdf", "#2fa84f", "#9b3fd6", "#e07b1f", "#c9a400", "#d63a3a"]  # match LED colours

LEFT   = [[(4,10),(4,9),(4,8),(4,7),(4,6)], [(5,10),(5,9),(5,8),(5,7),(5,6)], [(6,10),(6,9),(6,8),(6,7),(6,6)]]
RIGHT  = [[(0,0),(0,1),(0,2),(0,3),(0,4)],  [(1,0),(1,1),(1,2),(1,3),(1,4)],  [(2,0),(2,1),(2,2),(2,3),(2,4)]]
THUMBS = [(6,11),(5,11),(4,11), (0,5),(1,5),(2,5)]
ENC_PRESS = (3,0)

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = {int(k): v for k, v in json.load(open(os.path.join(HERE, "labels.json"), encoding="utf-8")).items()}
LABELS[0] = ""
NICE = {"LShift": "Shift", "LCtrl": "Ctrl", "LAlt": "Alt", "LGui": "Win", "RShift": "Shift", "RCtrl": "Ctrl", "RAlt": "AltGr", "RGui": "Win"}
CLIP = {0x11D: "Undo", 0x11C: "Redo", 0x106: "Copy", 0x119: "Paste", 0x11B: "Cut", 0xA16: "Screen\nshot", 0x7820: "LED\non/off", 0x7827: "LED\nbright +", 0x7828: "LED\nbright -"}

# ------------------------------------------------------------------ labels
def lname(n): return LAYER_NAMES[n] if n < len(LAYER_NAMES) else f"L{n}"

def mods(m):
    out = [n for b, n in ((1, "Ctrl"), (2, "Shift"), (4, "AltGr" if m & 0x10 else "Alt"), (8, "Win")) if m & b]
    return "+".join(out)

def label(code):
    """-> (main text, small hint text)"""
    if code in CLIP: return CLIP[code], ""
    if code in LABELS:
        t = LABELS[code]
        parts = t.split("\n")
        if code < 0x100 and len(parts) == 2 and all(len(p) == 1 for p in parts):
            t = parts[1]  # shifted pair like "!\n1": show what the key actually types
        return NICE.get(t, t), ""
    if 0x0100 <= code < 0x2000:
        return mods(code >> 8) + "+" + label(code & 0xFF)[0].replace("\n", " "), ""
    if 0x2000 <= code < 0x4000:
        return label(code & 0xFF)[0], "hold " + mods((code >> 8) & 0x1F)
    if 0x4000 <= code < 0x5000:
        return label(code & 0xFF)[0], "hold " + lname((code >> 8) & 0xF)
    for base, txt in ((0x5220, "MO"), (0x5200, "TO"), (0x5240, "DF"), (0x5260, "TG"), (0x5280, "OSL"), (0x52C0, "TT")):
        if base <= code < base + 0x20:
            return f"{txt}\n{lname(code & 0x1F)}", ""
    return hex(code), ""

def layer_key(code):
    """layer a held key switches to, or None"""
    if 0x4000 <= code < 0x5000: return (code >> 8) & 0xF
    if 0x5220 <= code < 0x5240 or 0x52C0 <= code < 0x52E0: return code & 0x1F
    return None

# ------------------------------------------------------------------ Win32 HID
if sys.platform == "win32":
    hid = ctypes.WinDLL("hid"); setupapi = ctypes.WinDLL("setupapi"); k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]
    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wt.DWORD), ("Reserved", ctypes.c_size_t)]
    class HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT), ("ProductID", wt.USHORT), ("VersionNumber", wt.USHORT)]
    class HIDP_CAPS(ctypes.Structure):
        _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT), ("InputReportByteLength", wt.USHORT),
                    ("OutputReportByteLength", wt.USHORT), ("FeatureReportByteLength", wt.USHORT),
                    ("Reserved", wt.USHORT * 17)] + [(n, wt.USHORT) for n in (
                    "NumberLinkCollectionNodes", "NumberInputButtonCaps", "NumberInputValueCaps", "NumberInputDataIndices",
                    "NumberOutputButtonCaps", "NumberOutputValueCaps", "NumberOutputDataIndices",
                    "NumberFeatureButtonCaps", "NumberFeatureValueCaps", "NumberFeatureDataIndices")]
    class OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", wt.DWORD),
                    ("OffsetHigh", wt.DWORD), ("hEvent", wt.HANDLE)]

    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wt.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    k32.CreateFileW.restype = wt.HANDLE
    k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
    k32.CreateEventW.restype = wt.HANDLE
    k32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
    k32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
    k32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
    k32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(wt.DWORD), wt.BOOL]
    k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    k32.CancelIo.argtypes = [wt.HANDLE]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    k32.ResetEvent.argtypes = [wt.HANDLE]
    hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
    hid.HidD_FlushQueue.argtypes = [wt.HANDLE]
    hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]

INVALID = ctypes.c_void_p(-1).value

class KeyboardGone(Exception): pass

class WinRawHid:
    def __init__(self, path):
        self.h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000000, None)  # RW, share RW, OPEN_EXISTING, OVERLAPPED
        if self.h in (None, INVALID): raise KeyboardGone("open failed")
        self.ev = k32.CreateEventW(None, True, False, None)
        self.flush()

    @staticmethod
    def find():
        g = GUID(); hid.HidD_GetHidGuid(ctypes.byref(g))
        info = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
        try:
            i = 0
            while True:
                d = SP_DEVICE_INTERFACE_DATA(); d.cbSize = ctypes.sizeof(d)
                if not setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(g), i, ctypes.byref(d)): return None
                i += 1
                need = wt.DWORD()
                setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(d), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value)
                ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if not setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(d), buf, need, None, None): continue
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if not any(i in path.lower() for i in IDS): continue
                h = k32.CreateFileW(path, 0, 3, None, 3, 0, None)
                if h in (None, INVALID): continue
                try:
                    pp = ctypes.c_void_p(); caps = HIDP_CAPS()
                    if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                        hid.HidP_GetCaps(pp, ctypes.byref(caps)); hid.HidD_FreePreparsedData(pp)
                        if caps.UsagePage == RAW_USAGE_PAGE: return path
                finally:
                    k32.CloseHandle(h)
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(info)

    def flush(self): hid.HidD_FlushQueue(self.h)

    def _io(self, fn, buf, n, timeout):
        ov = OVERLAPPED(); ov.hEvent = self.ev; k32.ResetEvent(self.ev); done = wt.DWORD()
        if not fn(self.h, buf, n, None, ctypes.byref(ov)):
            err = ctypes.get_last_error()
            if err != 997: raise KeyboardGone(f"io error {err}")
            if k32.WaitForSingleObject(self.ev, timeout) != 0:
                k32.CancelIo(self.h); k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(done), True)
                return None
        if not k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(done), True):
            raise KeyboardGone("io failed")
        return done.value

    def cmd(self, *data, match=True, timeout=300):
        out = ctypes.create_string_buffer(bytes([0] + list(data)).ljust(33, b"\0"), 33)
        if self._io(k32.WriteFile, out, 33, timeout) is None: raise KeyboardGone("write timeout")
        for _ in range(8):  # skip replies meant for other programs
            inp = ctypes.create_string_buffer(33)
            n = self._io(k32.ReadFile, inp, 33, timeout)
            if n is None: raise KeyboardGone("read timeout")
            r = inp.raw[1:33]
            if not match or r[0] == data[0] or r[0] == 0xFF: return r
        raise KeyboardGone("no matching reply")

    def close(self):
        k32.CloseHandle(self.h); k32.CloseHandle(self.ev)

class HidapiRawHid:
    """macOS / Linux, via the hidapi package (pip install hidapi)."""
    def __init__(self, path):
        import hid
        try:
            if hasattr(hid, "device"):          # cython-hidapi ("pip install hidapi")
                self.d = hid.device(); self.d.open_path(path)
                self._read = lambda t: bytes(self.d.read(32, t))
            else:                               # "pip install hid" (ctypes binding)
                self.d = hid.Device(path=path)
                self._read = lambda t: self.d.read(32, t) or b""
        except (OSError, IOError) as e:
            raise KeyboardGone(f"open failed: {e} (Linux: install the udev rule)")
        self.flush()

    @staticmethod
    def find():
        try: import hid
        except ImportError: sys.exit("Missing hidapi:  pip install hidapi")
        for d in hid.enumerate():
            if (d["vendor_id"], d["product_id"]) not in VIDPIDS: continue
            up = d.get("usage_page") or 0
            if up == RAW_USAGE_PAGE or (up == 0 and d.get("interface_number") == 1):  # old libusb backends report no usage page
                return d["path"]
        return None

    def flush(self):
        while self._read(0): pass

    def cmd(self, *data, match=True, timeout=300):
        try:
            self.d.write(bytes([0] + list(data)).ljust(33, b"\0"))
            for _ in range(8):  # skip replies meant for other programs
                r = self._read(timeout)
                if not r: raise KeyboardGone("read timeout")
                if len(r) == 33: r = r[1:]  # some backends keep the report id
                if not match or r[0] == data[0] or r[0] == 0xFF: return r
        except (OSError, IOError, ValueError) as e:
            raise KeyboardGone(str(e))
        raise KeyboardGone("no matching reply")

    def close(self):
        try: self.d.close()
        except Exception: pass

RawHid = WinRawHid if WIN and not os.environ.get("CHEAPINO_HIDAPI") else HidapiRawHid

class Board:
    ROWS, COLS = 8, 12
    def __init__(self, dev):
        self.dev = dev
        self.layers = dev.cmd(0x11)[1]
        self.mask = 1  # active layers bitmask
        self.read_keymap()
        self.fw_layer = dev.cmd(0x40)[0] == 0x40

    def read_keymap(self):
        total = self.layers * self.ROWS * self.COLS * 2
        raw = bytearray()
        for off in range(0, total, 28):
            n = min(28, total - off)
            raw += self.dev.cmd(0x12, off >> 8, off & 0xFF, n)[4:4 + n]
        k = [raw[i] << 8 | raw[i + 1] for i in range(0, total, 2)]
        self.keymap = [[[k[(l * self.ROWS + r) * self.COLS + c] for c in range(self.COLS)] for r in range(self.ROWS)] for l in range(self.layers)]
        self.encoders = []
        for l in range(self.layers):
            r = self.dev.cmd(0xFE, 0x03, l, 0, match=False)
            self.encoders.append((r[0] << 8 | r[1], r[2] << 8 | r[3]))

    def matrix(self):
        r = self.dev.cmd(0x02, 0x03)
        if r[0] != 0x02: return set()
        held = set()
        for row in range(self.ROWS):
            v = r[2 + row * 2] << 8 | r[3 + row * 2]
            for c in range(self.COLS):
                if v >> c & 1: held.add((row, c))
        return held

    def layer(self, held):
        if self.fw_layer:
            r = self.dev.cmd(0x40)
            self.mask = (r[2] | r[3] << 8 | r[4] << 16 | r[5] << 24) | 1
            return r[1]
        cur = 0
        for _ in range(3):
            self.mask = 1 | (1 << cur)
            nxt = 0
            for (r, c) in held:
                t = layer_key(self.resolve(cur, r, c))
                if t is not None and t < self.layers: nxt = max(nxt, t)
            if nxt == cur: break
            cur = nxt
        self.mask = 1 | (1 << cur)
        return cur

    def resolve(self, layer, r, c):
        for l in range(layer, -1, -1):
            if l != layer and l != 0 and not (self.mask >> l) & 1: continue  # inactive layers don't show through
            code = self.keymap[l][r][c]
            if code != 1: return code  # 1 = KC_TRNS
        return 0

def vial_running():
    try:
        if WIN:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Vial.exe", "/NH"], capture_output=True, text=True,
                                 creationflags=0x08000000, timeout=5).stdout
            return "vial.exe" in out.lower()
        out = subprocess.run(["ps", "-Ao", "comm="], capture_output=True, text=True, timeout=5).stdout
        return any(os.path.basename(l.strip()).lower().startswith("vial") for l in out.splitlines())
    except Exception:
        return False

# ------------------------------------------------------------------ worker thread
class State:
    def __init__(self):
        self.lock = threading.Lock(); self.status = "Looking for Cheapino..."
        self.board = None; self.layer = 0; self.held = frozenset(); self.reload = False; self.version = 0

def worker(st):
    dev = None; last_vial_check = 0; paused = False
    while True:
        try:
            if time.time() - last_vial_check > 0.5:
                last_vial_check = time.time()
                was, paused = paused, vial_running()
                if paused and not was:
                    with st.lock: st.status = "Paused while Vial is open"; st.version += 1
                if was and not paused and dev:
                    dev.flush(); st.reload = True
            if paused:
                time.sleep(0.3); continue
            if dev is None:
                path = RawHid.find()
                if not path:
                    with st.lock: st.status = "Cheapino not found (Vial firmware?)"; st.board = None; st.version += 1
                    time.sleep(2); continue
                dev = RawHid(path)
                b = Board(dev)
                with st.lock: st.board = b; st.status = ""; st.version += 1
            if st.reload:
                st.reload = False; st.board.read_keymap()
                with st.lock: st.version += 1
            held = st.board.matrix()
            layer = st.board.layer(held)
            with st.lock:
                if held != st.held or layer != st.layer:
                    st.held = frozenset(held); st.layer = layer; st.version += 1
            time.sleep(0.008)
        except (KeyboardGone, OSError, IndexError) as e:
            if dev: dev.close()
            dev = None
            with st.lock: st.status = "Reconnecting..."; st.board = None; st.version += 1
            time.sleep(1)

# ------------------------------------------------------------------ UI
def run_ui():
    import tkinter as tk
    if WIN:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    st = State(); threading.Thread(target=worker, args=(st,), daemon=True).start()

    root = tk.Tk(); root.title("Cheapino"); root.overrideredirect(True)
    root.attributes("-topmost", True); root.attributes("-alpha", 0.92)
    S = 1.0 if MAC else root.winfo_fpixels("1i") / 96.0  # Tk on macOS already works in points
    opts = {"autohide": tk.BooleanVar(value=False), "scale": 1.0}

    cv = tk.Canvas(root, bg="#1d2027", highlightthickness=0); cv.pack()
    drawn = {"v": -1}

    def geom():
        s = S * opts["scale"]; kw, kh, g, mid, pad, top = 60*s, 44*s, 5*s, 34*s, 10*s, 30*s
        W = pad*2 + 10*kw + 8*g + mid; H = top + 4*(kh+g) + 22*s + pad
        return s, kw, kh, g, mid, pad, top, W, H

    def key(x, y, w, h, code, sub_override, pressed, dim, color, s):
        main, sub = label(code)
        if sub_override: sub = sub_override
        fill = "#f2f2f2" if pressed else ("#2a2e37" if not dim else "#23262d")
        fg = "#111" if pressed else ("#e8e8e8" if not dim else "#6c717c")
        cv.create_rectangle(x, y, x+w, y+h, fill=fill, outline=color if pressed else "#3a3f4b", width=max(1, 2*s))
        main = main.replace("Mouse\n", "M.").replace("Media\n", "")
        lines = main.count("\n") + 1
        fs = max(6, int((11 if lines == 1 and len(main) <= 6 else 8) * s))
        cv.create_text(x+w/2, y+h/2 - (5*s if sub else 0), text=main, fill=fg, font=(FONT, fs, "bold"), justify="center")
        if sub:
            cv.create_text(x+w/2, y+h-8*s, text=sub, fill="#555" if pressed else color, font=(FONT, max(6, int(7*s))))

    def draw():
        with st.lock:
            v, b, layer, held, status = st.version, st.board, st.layer, st.held, st.status
        if v == drawn["v"]: return
        drawn["v"] = v
        s, kw, kh, g, mid, pad, top, W, H = geom()
        cv.config(width=W, height=H); cv.delete("all")
        hide = opts["autohide"].get() and b and not status and layer == 0
        if hide: root.withdraw(); return
        root.deiconify()
        color = LAYER_COLORS[layer] if layer < len(LAYER_COLORS) else "#888"
        cv.create_rectangle(0, 0, W, top-4*s, fill=color, width=0)
        title = status or f"{lname(layer)}" + (f"   ({LAYER_HOLD[layer]})" if layer in LAYER_HOLD else "")
        cv.create_text(pad, (top-4*s)/2, text=title, anchor="w", fill="white", font=(FONT, int(11*s), "bold"))
        if b and not b.fw_layer and not status:
            cv.create_text(W-pad, (top-4*s)/2, text="layer guessed from held keys", anchor="e", fill="#ddd", font=(FONT, int(7*s)))
        if not b or status: return
        def at(r, c):
            code = b.keymap[layer][r][c]
            dim = code == 1
            return (b.resolve(layer, r, c) if dim else code), dim
        for half, coords in ((0, LEFT), (1, RIGHT)):
            for ri, row in enumerate(coords):
                for ci, (r, c) in enumerate(row):
                    x = pad + (ci + half*5)*(kw+g) + half*(mid - g)
                    y = top + ri*(kh+g)
                    code, dim = at(r, c)
                    key(x, y, kw, kh, code, None, (r, c) in held, dim or code == 0, color, s)
        ty = top + 3*(kh+g) + 4*s
        for i, (r, c) in enumerate(THUMBS):
            col = 2 + i if i < 3 else 2 + i + 0
            x = pad + col*(kw+g) + (mid - g if i >= 3 else 0)
            code, dim = at(r, c)
            key(x, ty, kw, kh, code, None, (r, c) in held, dim or code == 0, color, s)
        # encoder
        e = b.encoders[layer] if layer < len(b.encoders) else (0, 0)
        if e[0] == 1 and e[1] == 1: e = b.encoders[0]
        press, _ = at(*ENC_PRESS)
        txt = f"Knob:  {label(e[0])[0]} / {label(e[1])[0]}    click: {label(press)[0]}".replace("\n", " ")
        cv.create_text(W/2, ty + kh + 13*s, text=txt, fill="#9aa0ac", font=(FONT, int(8*s)))

    def tick():
        draw(); root.after(30, tick)

    drag = {}
    def press(ev): drag.update(x=ev.x_root - root.winfo_x(), y=ev.y_root - root.winfo_y())
    def move(ev): root.geometry(f"+{ev.x_root - drag['x']}+{ev.y_root - drag['y']}")
    cv.bind("<ButtonPress-1>", press); cv.bind("<B1-Motion>", move)

    def resize(f): opts["scale"] = max(0.6, min(2.0, opts["scale"] * f)); drawn["v"] = -1
    menu = tk.Menu(root, tearoff=0)
    menu.add_checkbutton(label="Hide on base layer", variable=opts["autohide"], command=lambda: drawn.update(v=-1))
    menu.add_command(label="Reload keymap", command=lambda: setattr(st, "reload", True))
    menu.add_command(label="Bigger", command=lambda: resize(1.15))
    menu.add_command(label="Smaller", command=lambda: resize(1/1.15))
    menu.add_separator(); menu.add_command(label="Quit", command=root.destroy)
    for btn in (("<Button-2>", "<Control-Button-1>") if MAC else ("<Button-3>",)):  # Mac right-click is Button-2
        cv.bind(btn, lambda ev: menu.tk_popup(ev.x_root, ev.y_root))

    _, _, _, _, _, _, _, W, H = geom()
    root.geometry(f"+{int(root.winfo_screenwidth()/2 - W/2)}+{int(root.winfo_screenheight() - H - 80*S)}")
    tick(); root.mainloop()

def run_test():
    sys.stdout.reconfigure(encoding="utf-8")
    path = RawHid.find()
    print("raw HID path:", path)
    if not path: return
    dev = RawHid(path); b = Board(dev)
    print("layers:", b.layers, " firmware layer report:", b.fw_layer)
    for l in range(min(b.layers, 7)):
        print(f"layer {l} {lname(l):5}:", " ".join(label(b.keymap[l][r][c])[0].replace("\n", "/") for r, c in LEFT[1] + RIGHT[1]),
              "| thumbs:", " ".join(label(b.keymap[l][r][c])[0].replace("\n", "/") for r, c in THUMBS),
              "| knob:", [label(x)[0].replace("\n", " ") for x in b.encoders[l]])
    t = time.time(); n = 0
    while time.time() - t < 3:
        held = b.matrix(); n += 1
        if held: print("held:", sorted(held), "layer:", b.layer(held))
        time.sleep(0.05)
    print(f"{n} matrix polls in 3 s")
    dev.close()

def run_write(path):
    data = json.load(open(path))
    dev = RawHid(RawHid.find() or sys.exit("Cheapino not found")); b = Board(dev)
    keymap = data["keymap"][:b.layers]
    flat = bytearray()
    for l in range(b.layers):
        for r in range(b.ROWS):
            for c in range(b.COLS):
                code = keymap[l][r][c] if l < len(keymap) else b.keymap[l][r][c]
                flat += bytes([code >> 8, code & 0xFF])
    old = bytearray()
    for l in range(b.layers):
        for r in range(b.ROWS):
            for c in range(b.COLS):
                code = b.keymap[l][r][c]; old += bytes([code >> 8, code & 0xFF])
    changed = 0
    for off in range(0, len(flat), 28):
        chunk = flat[off:off + 28]
        if chunk != old[off:off + 28]:
            r = dev.cmd(0x13, off >> 8, off & 0xFF, len(chunk), *chunk)
            if r[0] != 0x13: sys.exit(f"write rejected at {off}")
            changed += 1
    enc = 0
    for l, layer in enumerate(data["encoders"][:b.layers]):
        for i, pair in enumerate(layer):
            for d, code in enumerate(pair):
                cur = b.encoders[l][d] if i == 0 else None
                if code != cur:
                    dev.cmd(0xFE, 0x04, l, i, d, code >> 8, code & 0xFF, match=False); enc += 1
    b.read_keymap()
    ok = all(b.keymap[l][r][c] == keymap[l][r][c] for l in range(len(keymap)) for r in range(b.ROWS) for c in range(b.COLS)) \
        and all(list(b.encoders[l]) == list(data["encoders"][l][0]) for l in range(min(len(data["encoders"]), b.layers)))
    print(f"wrote {changed} keymap chunks, {enc} knob settings; verified: {ok}")
    dev.close()

if __name__ == "__main__":
    if "--test" in sys.argv:
        print("backend:", RawHid.__name__); run_test()
    elif "--write" in sys.argv: run_write(sys.argv[sys.argv.index("--write") + 1])
    else: run_ui()
