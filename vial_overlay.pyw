"""Vial live keymap overlay.

An always-on-top window that draws your keyboard, shows the layer you are on and highlights the keys you
are holding. Works with any keyboard running Vial firmware: the physical layout, keymap and encoders are
read from the keyboard itself, so it stays correct after you change things in Vial (right-click > Reload).

Windows: no installs.  macOS / Linux: pip install hidapi  (Linux also needs the udev rule in linux/).

Layer detection:
  * firmware that answers the optional raw-HID 0x40 layer report -> exact (see README)
  * any other Vial firmware -> worked out from which layer keys (LT / MO / TT) are physically held

Run:   pythonw vial_overlay.pyw            (Windows, no console)   python3 vial_overlay.pyw &  (Mac/Linux)
Test:  python  vial_overlay.pyw --test     (prints what it reads, no window)
Write: python  vial_overlay.pyw --write keymap.json   (push a numeric keymap; close Vial first)

Optional settings: config.json next to this file (see config.example.json).
"""
import ctypes, json, lzma, math, os, struct, subprocess, sys, threading, time

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
RAW_USAGE_PAGE, RAW_USAGE = 0xFF60, 0x61      # VIA / Vial raw HID interface
FONT = "Segoe UI" if WIN else ("Helvetica Neue" if MAC else "DejaVu Sans")
HERE = os.path.dirname(os.path.abspath(__file__))

def load_config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return {}
    except ValueError as e: sys.exit(f"config.json is not valid JSON: {e}")
CONFIG = load_config()

def device_filter():
    """config "device": "vid:pid" (hex) -> (vid, pid) or None"""
    d = CONFIG.get("device")
    if not d: return None
    v, p = d.split(":")
    return int(v, 16), int(p, 16)

DEFAULT_COLORS = ["#4a5060", "#2f6fdf", "#2fa84f", "#9b3fd6", "#e07b1f", "#c9a400", "#d63a3a", "#1fa6a6",
                  "#d63a8f", "#6b8e23", "#8b5a2b", "#5f6fd6", "#b0436b", "#3f8f6f", "#a67c00", "#707070"]

# ------------------------------------------------------------------ labels
LABELS = {int(k): v for k, v in json.load(open(os.path.join(HERE, "labels.json"), encoding="utf-8")).items()}
LABELS[0] = ""
GUI = "Cmd" if MAC else "Win"
ALT = "Opt" if MAC else "Alt"
NICE = {"LShift": "Shift", "LCtrl": "Ctrl", "LAlt": ALT, "LGui": GUI, "RShift": "Shift", "RCtrl": "Ctrl",
        "RAlt": "AltGr", "RGui": GUI}
CLIP = {0x7820: "LED\non/off", 0x7827: "LED\nbright +", 0x7828: "LED\nbright -"}
for mod in (0x100, 0x800):  # Ctrl+ (Windows/Linux) and Cmd+ (Mac) clipboard shortcuts
    CLIP.update({mod | 0x1D: "Undo", mod | 0x1C: "Redo", mod | 0x06: "Copy", mod | 0x19: "Paste", mod | 0x1B: "Cut"})
CUSTOM = {}  # 0x7E00 + n -> name, from the keyboard definition's customKeycodes

def layer_name(n):
    names = CONFIG.get("layer_names") or []
    return names[n] if n < len(names) and names[n] else f"Layer {n}"

def layer_color(n):
    cols = CONFIG.get("layer_colors") or []
    return cols[n] if n < len(cols) and cols[n] else DEFAULT_COLORS[n % len(DEFAULT_COLORS)]

def mods(m):
    return "+".join(n for b, n in ((1, "Ctrl"), (2, "Shift"), (4, "AltGr" if m & 0x10 else ALT), (8, GUI)) if m & b)

def label(code):
    """-> (main text, small hint text)"""
    if code in CLIP: return CLIP[code], ""
    if code in CUSTOM: return CUSTOM[code], ""
    if code in LABELS:
        t = LABELS[code]
        parts = t.split("\n")
        if code < 0x100 and len(parts) == 2 and all(len(p) == 1 for p in parts):
            t = parts[1]  # shifted pair like "!\n1": show what the key actually types
        return NICE.get(t, t), ""
    if 0x0100 <= code < 0x2000:
        pair = LABELS.get(code & 0xFF, "").split("\n")
        if code >> 8 in (0x02, 0x12) and len(pair) == 2 and len(pair[0]) == 1:
            return pair[0], ""  # Shift + a symbol key: show the shifted symbol, e.g. "
        return mods(code >> 8) + "+" + label(code & 0xFF)[0].replace("\n", " "), ""
    if 0x2000 <= code < 0x4000:
        return label(code & 0xFF)[0], "hold " + mods((code >> 8) & 0x1F)
    if 0x4000 <= code < 0x5000:
        return label(code & 0xFF)[0], "hold " + layer_name((code >> 8) & 0xF)
    for base, txt in ((0x5220, "MO"), (0x5200, "TO"), (0x5240, "DF"), (0x5260, "TG"), (0x5280, "OSL"), (0x52C0, "TT")):
        if base <= code < base + 0x20:
            return f"{txt}\n{layer_name(code & 0x1F)}", ""
    return hex(code), ""

def layer_key(code):
    """layer a held key switches to, or None"""
    if 0x4000 <= code < 0x5000: return (code >> 8) & 0xF
    if 0x5220 <= code < 0x5240 or 0x52C0 <= code < 0x52E0: return code & 0x1F
    return None

# ------------------------------------------------------------------ KLE layout (from the Vial definition)
# KLE stores up to 12 legends per key in an order that depends on the alignment flag "a".
KLE_LABEL_MAP = [
    [0, 6, 2, 8, 9, 11, 3, 5, 1, 4, 7, 10], [1, 7, -1, -1, 9, 11, 4, -1, -1, -1, -1, 10],
    [3, -1, 5, -1, 9, 11, -1, -1, 4, -1, -1, 10], [4, -1, -1, -1, 9, 11, -1, -1, -1, -1, -1, 10],
    [0, 6, 2, 8, 10, -1, 3, 5, 1, 4, 7, -1], [1, 7, -1, -1, 10, -1, 4, -1, -1, -1, -1, -1],
    [3, -1, 5, -1, 10, -1, -1, -1, 4, -1, -1, -1], [4, -1, -1, -1, 10, -1, -1, -1, -1, -1, -1, -1]]

def parse_kle(rows):
    """-> list of dicts: x, y, w, h, r, rx, ry (key units) plus 'rc' (row, col) or 'enc' (idx, dir), and 'opt'."""
    keys = []
    r = rx = ry = 0.0; cx = cy = 0.0; x = y = 0.0; w = h = 1.0; align = 4; decal = False
    for row in rows:
        if not isinstance(row, list): continue  # keyboard metadata object
        for item in row:
            if isinstance(item, dict):
                if "r" in item: r = item["r"]
                if "rx" in item: rx = cx = item["rx"]; x, y = cx, cy
                if "ry" in item: ry = cy = item["ry"]; x, y = cx, cy
                if "a" in item: align = item["a"]
                x += item.get("x", 0); y += item.get("y", 0)
                if "w" in item: w = item["w"]
                if "h" in item: h = item["h"]
                if item.get("d"): decal = True
                continue
            legends = [""] * 12
            for i, t in enumerate(str(item).split("\n")[:12]):
                pos = KLE_LABEL_MAP[align if 0 <= align < 8 else 4][i]
                if pos >= 0: legends[pos] = t
            k = {"x": x, "y": y, "w": w, "h": h, "r": r, "rx": rx, "ry": ry, "rc": None, "enc": None, "opt": None}
            try:
                if legends[4] == "e":
                    k["enc"] = tuple(int(v) for v in legends[0].split(","))
                elif not decal and "," in legends[0]:
                    k["rc"] = tuple(int(v) for v in legends[0].split(","))
                if legends[8] and "," in legends[8]:
                    k["opt"] = tuple(int(v) for v in legends[8].split(","))
            except ValueError:
                pass
            if k["rc"] or k["enc"]: keys.append(k)
            x += w; w = h = 1.0; decal = False
        y += 1; x = rx  # KLE: a new row starts at the rotation origin's x
    return keys

def corners(k, inset=0.0):
    a = math.radians(k["r"]); ca, sa = math.cos(a), math.sin(a)
    pts = []
    for px, py in ((k["x"] + inset, k["y"] + inset), (k["x"] + k["w"] - inset, k["y"] + inset),
                   (k["x"] + k["w"] - inset, k["y"] + k["h"] - inset), (k["x"] + inset, k["y"] + k["h"] - inset)):
        dx, dy = px - k["rx"], py - k["ry"]
        pts.append((k["rx"] + dx * ca - dy * sa, k["ry"] + dx * sa + dy * ca))
    return pts

def option_choices(labels, value):
    """Vial layout options bitfield -> {option index: chosen value}"""
    out, shift = {}, 0
    for i in range(len(labels) - 1, -1, -1):
        lbl = labels[i]
        n = 2 if isinstance(lbl, str) else max(2, len(lbl) - 1)
        bits = (n - 1).bit_length()
        out[i] = (value >> shift) & ((1 << bits) - 1); shift += bits
    return out

# ------------------------------------------------------------------ HID transport
class KeyboardGone(Exception): pass

if WIN:
    import ctypes.wintypes as wt
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

class WinRawHid:
    def __init__(self, path):
        self.h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000000, None)  # RW, share RW, OPEN_EXISTING, OVERLAPPED
        if self.h in (None, INVALID): raise KeyboardGone("open failed")
        self.ev = k32.CreateEventW(None, True, False, None)
        self.flush()

    @staticmethod
    def candidates():
        """raw HID interfaces with the VIA/Vial usage page -> [(path, vid, pid)]"""
        found = []
        g = GUID(); hid.HidD_GetHidGuid(ctypes.byref(g))
        info = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
        try:
            i = 0
            while True:
                d = SP_DEVICE_INTERFACE_DATA(); d.cbSize = ctypes.sizeof(d)
                if not setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(g), i, ctypes.byref(d)): break
                i += 1
                need = wt.DWORD()
                setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(d), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value)
                ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if not setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(d), buf, need, None, None): continue
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                h = k32.CreateFileW(path, 0, 3, None, 3, 0, None)  # no access rights needed to read attributes
                if h in (None, INVALID): continue
                try:
                    attr = HIDD_ATTRIBUTES(); attr.Size = ctypes.sizeof(attr)
                    pp = ctypes.c_void_p(); caps = HIDP_CAPS()
                    if hid.HidD_GetAttributes(h, ctypes.byref(attr)) and hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                        hid.HidP_GetCaps(pp, ctypes.byref(caps)); hid.HidD_FreePreparsedData(pp)
                        if caps.UsagePage == RAW_USAGE_PAGE and caps.Usage == RAW_USAGE:
                            found.append((path, attr.VendorID, attr.ProductID))
                finally:
                    k32.CloseHandle(h)
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(info)
        return found

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
    def candidates():
        try: import hid
        except ImportError: sys.exit("Missing hidapi:  pip install hidapi")
        found = []
        for d in hid.enumerate():
            up = d.get("usage_page") or 0
            # old libusb backends report no usage page; VIA/Vial firmware always puts raw HID on interface 1
            if (up == RAW_USAGE_PAGE and d.get("usage") in (RAW_USAGE, 0)) or (up == 0 and d.get("interface_number") == 1):
                found.append((d["path"], d["vendor_id"], d["product_id"]))
        return found

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

RawHid = WinRawHid if WIN and not os.environ.get("VIAL_OVERLAY_HIDAPI") else HidapiRawHid

def open_vial():
    """First Vial keyboard found (optionally filtered by config "device") -> (RawHid, vial protocol, uid) or None"""
    want = device_filter()
    for path, vid, pid in RawHid.candidates():
        if want and (vid, pid) != want: continue
        try:
            dev = RawHid(path)
        except KeyboardGone:
            continue
        try:
            r = dev.cmd(0xFE, 0x00, match=False)          # Vial: get keyboard id
            proto, uid = struct.unpack("<IQ", r[:12])
            if r[0] != 0xFF and proto < 0x100:            # plain VIA firmware answers 0xFF (unhandled)
                return dev, proto, uid
        except KeyboardGone:
            pass
        dev.close()
    return None

# ------------------------------------------------------------------ keyboard model
class Board:
    def __init__(self, dev, proto, uid):
        self.dev, self.proto, self.uid = dev, proto, uid
        self.definition = self.read_definition()
        self.name = self.definition.get("name", "Vial keyboard")
        self.rows = self.definition["matrix"]["rows"]; self.cols = self.definition["matrix"]["cols"]
        self.keys = parse_kle(self.definition["layouts"]["keymap"])
        self.n_enc = max([k["enc"][0] + 1 for k in self.keys if k["enc"]] + [0])
        CUSTOM.clear()
        for i, ck in enumerate(self.definition.get("customKeycodes") or []):
            CUSTOM[0x7E00 + i] = ck.get("shortName") or ck.get("name") or f"USER{i}"
        self.layers = dev.cmd(0x11)[1]
        self.mask = 1  # active layers bitmask
        self.read_keymap()
        self.fw_layer = bool(CONFIG.get("firmware_layer_report")) and dev.cmd(0x40)[0] == 0x40

    def read_definition(self):
        size = struct.unpack("<I", self.dev.cmd(0xFE, 0x01, match=False)[:4])[0]
        if not 0 < size < 1 << 20: raise KeyboardGone(f"bad definition size {size}")
        blob = bytearray()
        for block in range((size + 31) // 32):
            blob += self.dev.cmd(*struct.pack("<BBI", 0xFE, 0x02, block), match=False)
        return json.loads(lzma.decompress(bytes(blob[:size])))

    def read_keymap(self):
        total = self.layers * self.rows * self.cols * 2
        raw = bytearray()
        for off in range(0, total, 28):
            n = min(28, total - off)
            raw += self.dev.cmd(0x12, off >> 8, off & 0xFF, n)[4:4 + n]
        k = [raw[i] << 8 | raw[i + 1] for i in range(0, total, 2)]
        self.keymap = [[[k[(l * self.rows + r) * self.cols + c] for c in range(self.cols)] for r in range(self.rows)]
                       for l in range(self.layers)]
        self.encoders = []
        for l in range(self.layers):
            per = []
            for i in range(self.n_enc):
                r = self.dev.cmd(0xFE, 0x03, l, i, match=False)
                per.append((r[0] << 8 | r[1], r[2] << 8 | r[3]))
            self.encoders.append(per)
        labels = self.definition["layouts"].get("labels")
        choice = {}
        if labels:
            r = self.dev.cmd(0x02, 0x02)                   # VIA: layout options
            choice = option_choices(labels, struct.unpack(">I", r[2:6])[0]) if r[0] == 0x02 else {}
        self.visible = [k for k in self.keys if not k["opt"] or choice.get(k["opt"][0], 0) == k["opt"][1]]
        self.hold_hint = {}
        for (r, c) in {k["rc"] for k in self.visible if k["rc"]}:
            code = self.keymap[0][r][c] if r < self.rows and c < self.cols else 0
            t = layer_key(code)
            if t and t not in self.hold_hint:
                self.hold_hint[t] = "hold " + (label(code & 0xFF)[0].replace("\n", " ") if code < 0x5000 else "its MO key")

    def matrix(self):
        r = self.dev.cmd(0x02, 0x03)                       # VIA: switch matrix state (needs Vial unlocked or VIAL_INSECURE)
        bpr = self.cols // 8 + 1
        if r[0] != 0x02 or 2 + self.rows * bpr > 32: return set()
        held = set()
        for row in range(self.rows):
            v = int.from_bytes(r[2 + row * bpr: 2 + (row + 1) * bpr], "big")
            for c in range(self.cols):
                if v >> c & 1: held.add((row, c))
        return held

    def layer(self, held):
        if self.fw_layer:
            r = self.dev.cmd(0x40)
            self.mask = (r[2] | r[3] << 8 | r[4] << 16 | r[5] << 24) | 1
            return r[1]
        cur = 0
        for _ in range(4):
            self.mask = 1 | (1 << cur)
            nxt = 0
            for (r, c) in held:
                t = layer_key(self.resolve(cur, r, c))
                if t is not None and t < self.layers: nxt = max(nxt, t)
            if nxt == cur: break
            cur = nxt
        self.mask = 1 | (1 << cur)
        return cur

    def _fall(self, layer, get):
        for l in range(layer, -1, -1):
            if l != layer and l != 0 and not (self.mask >> l) & 1: continue  # inactive layers don't show through
            code = get(l)
            if code != 1: return code  # 1 = KC_TRNS
        return 0

    def resolve(self, layer, r, c):
        if r >= self.rows or c >= self.cols: return 0
        return self._fall(layer, lambda l: self.keymap[l][r][c])

    def resolve_enc(self, layer, idx, d):
        return self._fall(layer, lambda l: self.encoders[l][idx][d])

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
        self.lock = threading.Lock(); self.status = "Looking for a Vial keyboard..."
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
                found = open_vial()
                if not found:
                    with st.lock: st.status = "No Vial keyboard found"; st.board = None; st.version += 1
                    time.sleep(2); continue
                dev = found[0]
                b = Board(*found)
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
        except (KeyboardGone, OSError, IndexError, KeyError, ValueError, lzma.LZMAError) as e:
            if dev: dev.close()
            dev = None
            with st.lock: st.status = f"Reconnecting... ({e.__class__.__name__})"; st.board = None; st.version += 1
            time.sleep(1)

# ------------------------------------------------------------------ UI
def run_ui():
    import tkinter as tk
    if WIN:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    st = State(); threading.Thread(target=worker, args=(st,), daemon=True).start()

    root = tk.Tk(); root.title("Vial overlay"); root.overrideredirect(True)
    root.attributes("-topmost", True); root.attributes("-alpha", float(CONFIG.get("opacity", 0.92)))
    S = 1.0 if MAC else root.winfo_fpixels("1i") / 96.0  # Tk on macOS already works in points
    opts = {"autohide": tk.BooleanVar(value=False), "scale": float(CONFIG.get("scale", 1.0)), "placed": False}

    cv = tk.Canvas(root, bg="#1d2027", highlightthickness=0); cv.pack()
    drawn = {"v": -1}

    def draw_key(pts, cx, cy, ang, w, h, code, pressed, dim, color, s, oval=False):
        main, sub = label(code)
        fill = "#f2f2f2" if pressed else ("#2a2e37" if not dim else "#23262d")
        fg = "#111" if pressed else ("#e8e8e8" if not dim else "#6c717c")
        outline = color if pressed else "#3a3f4b"
        if oval:
            rad = min(w, h) / 2
            cv.create_oval(cx - rad, cy - rad, cx + rad, cy + rad, fill=fill, outline=outline, width=max(1, 2 * s))
        else:
            cv.create_polygon([c for p in pts for c in p], fill=fill, outline=outline, width=max(1, 2 * s))
        main = main.replace("Mouse\n", "M.").replace("Media\n", "")
        lines = main.count("\n") + 1
        longest = max(len(t) for t in main.split("\n")) if main else 1
        fs = max(6, int(min(11, 0.2 * w / s * 6 / max(4, longest) * 1.2, 0.28 * h / s / lines * 1.3) * s))
        a = math.radians(ang); dx, dy = -math.sin(a), math.cos(a)  # "down" direction of the rotated key
        off = 0.11 * h if sub else 0
        cv.create_text(cx - dx * off, cy - dy * off, text=main, fill=fg, font=(FONT, fs, "bold"), justify="center", angle=-ang)
        if sub:
            cv.create_text(cx + dx * 0.32 * h, cy + dy * 0.32 * h, text=sub, fill="#555" if pressed else color,
                           font=(FONT, max(6, int(7 * s))), angle=-ang)

    def draw():
        with st.lock:
            v, b, layer, held, status = st.version, st.board, st.layer, st.held, st.status
        if v == drawn["v"]: return
        drawn["v"] = v
        s = S * opts["scale"]; u = 54 * s; pad, top = 10 * s, 30 * s
        cv.delete("all")
        keys = b.visible if b and not status else []
        if keys:
            allpts = [p for k in keys for p in corners(k)]
            minx, miny = min(p[0] for p in allpts), min(p[1] for p in allpts)
            W = (max(p[0] for p in allpts) - minx) * u + 2 * pad; H = top + (max(p[1] for p in allpts) - miny) * u + pad
        else:
            minx = miny = 0; W, H = 420 * s, top + 10 * s
        cv.config(width=W, height=H)
        if opts["autohide"].get() and b and not status and layer == 0: root.withdraw(); return
        root.deiconify()
        color = layer_color(layer)
        cv.create_rectangle(0, 0, W, top - 4 * s, fill=color, width=0)
        hint = b.hold_hint.get(layer) if b else None
        title = status or layer_name(layer) + (f"   ({hint})" if hint else "")
        cv.create_text(pad, (top - 4 * s) / 2, text=title, anchor="w", fill="white", font=(FONT, int(11 * s), "bold"))
        if b and not status:
            note = b.name if b.fw_layer else f"{b.name} · layer guessed from held keys"
            cv.create_text(W - pad, (top - 4 * s) / 2, text=note, anchor="e", fill="#ddd", font=(FONT, int(7 * s)))
        if not keys: return
        to_px = lambda p: (pad + (p[0] - minx) * u, top + (p[1] - miny) * u)
        for k in keys:
            pts = [to_px(p) for p in corners(k, 0.05)]
            cx = sum(p[0] for p in pts) / 4; cy = sum(p[1] for p in pts) / 4
            w, h = (k["w"] - 0.1) * u, (k["h"] - 0.1) * u
            if k["enc"]:
                idx, d = k["enc"]
                code = b.resolve_enc(layer, idx, d) if idx < b.n_enc and d in (0, 1) else 0
                own = b.encoders[layer][idx][d] if idx < b.n_enc and d in (0, 1) else 0
                draw_key(pts, cx, cy, k["r"], w, h, code, False, own == 1 or code == 0, color, s, oval=True)
            else:
                r, c = k["rc"]
                own = b.keymap[layer][r][c] if r < b.rows and c < b.cols else 0
                code = b.resolve(layer, r, c)
                draw_key(pts, cx, cy, k["r"], w, h, code, (r, c) in held, own == 1 or code == 0, color, s)
        if not opts["placed"]:
            opts["placed"] = True
            root.update_idletasks()
            root.geometry(f"+{int(root.winfo_screenwidth() / 2 - W / 2)}+{int(root.winfo_screenheight() - H - 80 * S)}")

    def tick():
        draw(); root.after(30, tick)

    drag = {}
    def press(ev): drag.update(x=ev.x_root - root.winfo_x(), y=ev.y_root - root.winfo_y())
    def move(ev): root.geometry(f"+{ev.x_root - drag['x']}+{ev.y_root - drag['y']}")
    cv.bind("<ButtonPress-1>", press); cv.bind("<B1-Motion>", move)

    def resize(f): opts["scale"] = max(0.5, min(2.5, opts["scale"] * f)); drawn["v"] = -1
    menu = tk.Menu(root, tearoff=0)
    menu.add_checkbutton(label="Hide on base layer", variable=opts["autohide"], command=lambda: drawn.update(v=-1))
    menu.add_command(label="Reload keymap", command=lambda: setattr(st, "reload", True))
    menu.add_command(label="Bigger", command=lambda: resize(1.15))
    menu.add_command(label="Smaller", command=lambda: resize(1 / 1.15))
    menu.add_separator(); menu.add_command(label="Quit", command=root.destroy)
    for btn in (("<Button-2>", "<Control-Button-1>") if MAC else ("<Button-3>",)):  # Mac right-click is Button-2
        cv.bind(btn, lambda ev: menu.tk_popup(ev.x_root, ev.y_root))

    root.geometry(f"+{int(root.winfo_screenwidth() / 2 - 210 * S)}+{int(root.winfo_screenheight() - 200 * S)}")
    tick(); root.mainloop()

# ------------------------------------------------------------------ command line modes
def connect():
    found = open_vial()
    if not found: sys.exit("No Vial keyboard found" + (" matching config device" if device_filter() else ""))
    return found[0], Board(*found)

def run_test():
    sys.stdout.reconfigure(encoding="utf-8")
    print("backend:", RawHid.__name__)
    for path, vid, pid in RawHid.candidates(): print(f"  raw HID {vid:04x}:{pid:04x}  {path}")
    dev, b = connect()
    print(f"keyboard: {b.name}  uid {b.uid:#018x}  vial protocol {b.proto}  matrix {b.rows}x{b.cols}  layers {b.layers}"
          f"  keys {len(b.visible)}  encoders {b.n_enc}  firmware layer report: {b.fw_layer}")
    order = sorted((k for k in b.visible if k["rc"]), key=lambda k: (round(k["y"]), k["x"]))
    for l in range(b.layers):
        if l and all(b.keymap[l][r][c] in (0, 1) for r in range(b.rows) for c in range(b.cols)): continue
        print(f"{layer_name(l):>10}:", " ".join(label(b.resolve(l, *k['rc']))[0].replace("\n", "/") or "." for k in order),
              "| knobs:", [tuple(label(x)[0].replace("\n", " ") for x in e) for e in b.encoders[l]])
    print("hold hints:", b.hold_hint)
    t = time.time(); n = 0
    while time.time() - t < 3:
        held = b.matrix(); n += 1
        if held: print("held:", sorted(held), "layer:", b.layer(held))
        time.sleep(0.05)
    print(f"{n} matrix polls in 3 s")
    dev.close()

def run_write(path):
    data = json.load(open(path))
    dev, b = connect()
    keymap = data["keymap"][:b.layers]
    if keymap and (len(keymap[0]) != b.rows or len(keymap[0][0]) != b.cols):
        sys.exit(f"keymap is {len(keymap[0])}x{len(keymap[0][0])} but {b.name} has a {b.rows}x{b.cols} matrix")
    pack = lambda get: b"".join(struct.pack(">H", get(l, r, c)) for l in range(b.layers) for r in range(b.rows) for c in range(b.cols))
    flat = pack(lambda l, r, c: keymap[l][r][c] if l < len(keymap) else b.keymap[l][r][c])
    old = pack(lambda l, r, c: b.keymap[l][r][c])
    changed = 0
    for off in range(0, len(flat), 28):
        chunk = flat[off:off + 28]
        if chunk != old[off:off + 28]:
            if dev.cmd(0x13, off >> 8, off & 0xFF, len(chunk), *chunk)[0] != 0x13: sys.exit(f"write rejected at {off}")
            changed += 1
    enc = 0
    want_enc = data.get("encoders", [])[:b.layers]
    for l, layer in enumerate(want_enc):
        for i, pair in enumerate(layer[:b.n_enc]):
            for d, code in enumerate(pair[:2]):
                if code != b.encoders[l][i][d]:
                    dev.cmd(0xFE, 0x04, l, i, d, code >> 8, code & 0xFF, match=False); enc += 1
    b.read_keymap()
    ok = all(b.keymap[l][r][c] == keymap[l][r][c] for l in range(len(keymap)) for r in range(b.rows) for c in range(b.cols)) \
        and all(list(b.encoders[l][i]) == list(want_enc[l][i][:2]) for l in range(len(want_enc)) for i in range(min(b.n_enc, len(want_enc[l]))))
    print(f"wrote {changed} keymap chunks, {enc} knob settings; verified: {ok}")
    dev.close()

if __name__ == "__main__":
    if "--test" in sys.argv: run_test()
    elif "--write" in sys.argv: run_write(sys.argv[sys.argv.index("--write") + 1])
    else: run_ui()
