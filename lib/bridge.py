#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开发模式 · Windows 侧常驻助手（用 pythonw 启动：无控制台 → 零闪窗、零冷启动开销）

通道：文件队列（WSL 目录经 \\wsl.localhost 暴露），无需网络配置、免防火墙。
协议：WSL 写 queue/cmd-<id>.json → 助手执行 → 写 queue/res-<id>.json
"""
import ctypes, ctypes.wintypes as wt, glob, json, os, struct, sys, time, traceback, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
_LOG = os.path.join(os.path.dirname(HERE), "bridge.log")

def log(msg):
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%F %T"), msg))
    except Exception:
        pass

log("boot __file__=%r cwd=%r" % (__file__, os.getcwd()))
ROOT = os.path.dirname(HERE)
QUEUE = os.path.join(ROOT, "queue")
PIDF = os.path.join(ROOT, "bridge.pid")
HB = os.path.join(ROOT, "bridge.heartbeat")

# ---------- DPI：per-monitor v2，坐标统一用物理像素（与截图一致） ----------
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32

# 显式声明 64 位句柄的 restype/argtypes —— 否则 shot 会报
# "OverflowError: int too long to convert"（gdi32 句柄被当作 c_int 处理）
g32.CreateCompatibleDC.restype = ctypes.c_void_p
g32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
g32.CreateCompatibleBitmap.restype = ctypes.c_void_p
g32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
g32.SelectObject.restype = ctypes.c_void_p
g32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
g32.DeleteObject.argtypes = [ctypes.c_void_p]
g32.DeleteDC.argtypes = [ctypes.c_void_p]
g32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

# BitBlt：**漏了它**就时灵时不灵 —— 内存 DC 句柄是 64 位指针，
# 未声明时 ctypes 按 c_int 转换：句柄 < 2^31 侥幸能过，≥ 2^31 就
# "argument 1: int too long to convert"。2026-09-28 修。
g32.BitBlt.restype = ctypes.c_int
g32.BitBlt.argtypes = [ctypes.c_void_p,            # hdcDest
                       ctypes.c_int, ctypes.c_int,  # x, y
                       ctypes.c_int, ctypes.c_int,  # w, h
                       ctypes.c_void_p,             # hdcSrc
                       ctypes.c_int, ctypes.c_int,  # x1, y1
                       ctypes.c_uint]               # rop

u32.GetDC.restype = ctypes.c_void_p
u32.GetDC.argtypes = [ctypes.c_void_p]
u32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

# 窗口句柄（HWND）同样是 64 位；一并声明，免得将来同样翻车
u32.GetForegroundWindow.restype = ctypes.c_void_p
u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
u32.IsWindowVisible.restype = ctypes.c_bool
u32.IsIconic.argtypes = [ctypes.c_void_p]
u32.IsIconic.restype = ctypes.c_bool
u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u32.GetWindowRect.restype = ctypes.c_bool
u32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
u32.GetWindowTextLengthW.restype = ctypes.c_int
u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
u32.GetWindowTextW.restype = ctypes.c_int
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u32.GetWindowThreadProcessId.restype = ctypes.c_ulong
u32.IsWindow.argtypes = [ctypes.c_void_p]
u32.IsWindow.restype = ctypes.c_bool
u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u32.SetForegroundWindow.restype = ctypes.c_bool
u32.BringWindowToTop.argtypes = [ctypes.c_void_p]
u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.SwitchToThisWindow.argtypes = [ctypes.c_void_p, ctypes.c_bool]
u32.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.AllowSetForegroundWindow.argtypes = [ctypes.c_uint]

# ---------- 抓屏 ----------
class BIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

def _vrect():
    return (u32.GetSystemMetrics(76), u32.GetSystemMetrics(77),
            u32.GetSystemMetrics(78), u32.GetSystemMetrics(79))  # x, y, w, h

def _png(path, w, h, rgb):
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw += b"\x00" + bytes(rgb[y*stride:(y+1)*stride])
    def ch(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n"
    data += ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += ch(b"IDAT", zlib.compress(bytes(raw), 6))
    data += ch(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)

def shot(out, fmt="png"):
    vsx, vsy, vw, vh = _vrect()
    hdc = u32.GetDC(0)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, vw, vh)
    g32.SelectObject(mdc, bmp)
    g32.BitBlt(mdc, 0, 0, vw, vh, hdc, vsx, vsy, 0x00CC0020)
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = vw; bi.biHeight = -vh
    bi.biPlanes = 1; bi.biBitCount = 32; bi.biCompression = 0
    buf = ctypes.create_string_buffer(vw * vh * 4)
    g32.GetDIBits(mdc, bmp, 0, vh, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(0, hdc)
    b = buf.raw                                        # BGRA，top-down
    unc = "\\\\wsl.localhost\\Ubuntu" + out.replace("/", "\\")
    os.makedirs(os.path.dirname(unc), exist_ok=True)
    if fmt == "bmp":                                   # 给 numpy 做匹配用（免解码依赖）
        row = vw * 4
        hdr = struct.pack("<2sIHHI", b"BM", 14 + 40 + row * vh, 0, 0, 14 + 40)
        info = struct.pack("<IiiHHIIiiII", 40, vw, -vh, 1, 32, 0, row * vh, 2835, 2835, 0, 0)
        with open(unc, "wb") as f:
            f.write(hdr + info + b)
    else:
        rgb = bytearray(vw * vh * 3)
        j = 0
        for i in range(0, len(b), 4):
            rgb[j] = b[i+2]; rgb[j+1] = b[i+1]; rgb[j+2] = b[i]; j += 3
        _png(unc, vw, vh, rgb)
    return {"path": out, "w": vw, "h": vh, "fmt": fmt, "bytes": os.path.getsize(unc)}

# ---------- 窗口 ----------
def _proc_name(pid):
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(512); n = wt.DWORD(512)
    k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k32.CloseHandle(h)
    return os.path.basename(buf.value)

def _wtitle(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    b = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, b, n + 1)
    return b.value

def windows():
    out = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, l):
        if not u32.IsWindowVisible(hwnd):
            return True
        t = _wtitle(hwnd)
        if not t:
            return True
        r = wt.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
        pid = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append({"hwnd": int(hwnd), "title": t, "pid": int(pid.value),
                    "exe": _proc_name(pid.value),
                    "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top],
                    "minimized": bool(u32.IsIconic(hwnd))})
        return True
    u32.EnumWindows(CB(cb), 0)
    return out

def foreground():
    h = u32.GetForegroundWindow()
    r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return {"hwnd": int(h), "title": _wtitle(h), "exe": _proc_name(pid.value),
            "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top]}

def focus(match):
    m = match.lower()
    for w_ in windows():
        if m in w_["title"].lower():
            h = w_["hwnd"]
            if u32.IsIconic(h):
                u32.ShowWindow(h, 9)          # SW_RESTORE
            try:
                u32.AllowSetForegroundWindow(ctypes.c_uint(-1))   # ASFW_ANY
            except Exception:
                pass
            u32.SwitchToThisWindow(h, True)
            u32.SetForegroundWindow(h)
            u32.BringWindowToTop(h)
            time.sleep(0.2)
            return {"focused": w_, "now": foreground()}
    return {"focused": None, "error": "未找到匹配窗口"}

# ---------- 手：SendInput ----------
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]
class _UN(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _UN)]

MOVE, LEFTDN, LEFTUP, RIGHTDN, RIGHTUP = 0x0001, 0x0002, 0x0004, 0x0008, 0x0010
ABSOLUTE, VIRTUALDESK, UNICODE, KEYUP = 0x8000, 0x4000, 0x0004, 0x0002

def _send(i):
    u32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))

def _mouse(flags, x=None, y=None):
    i = INPUT(type=0)
    dx = dy = 0
    if x is not None:
        vsx, vsy, vw, vh = _vrect()
        dx = int((x - vsx) * 65535 / max(vw - 1, 1))
        dy = int((y - vsy) * 65535 / max(vh - 1, 1))
        flags |= MOVE | ABSOLUTE | VIRTUALDESK
    i.u.mi = MOUSEINPUT(dx, dy, 0, flags, 0, None)
    _send(i)

def move(x, y):
    _mouse(0, x, y); time.sleep(0.05)
    return {"moved": [x, y]}

def click(x=None, y=None, button="left", double=False, times=1):
    if x is not None:
        move(x, y)
    dn, up = (LEFTDN, LEFTUP) if button == "left" else (RIGHTDN, RIGHTUP)
    for _ in range(2 if double else times):
        _mouse(dn); time.sleep(0.02); _mouse(up); time.sleep(0.05)
    return {"clicked": button, "at": [x, y], "double": double}

VK = {**{c: 0x41 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")},
      **{c: 0x30 + i for i, c in enumerate("0123456789")},
      "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20, "backspace": 0x08,
      "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
      "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
      "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
      "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
      "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}

def _key_vk(vk, up=False):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(vk, 0, KEYUP if up else 0, 0, None)
    _send(i)

def key(combo):
    parts = [p.strip().lower() for p in combo.replace(" ", "").split("+")]
    vks = [VK[p] for p in parts]
    for v in vks:
        _key_vk(v)
    for v in reversed(vks):
        _key_vk(v, True)
    time.sleep(0.05)
    return {"key": combo}

def type_text(text):
    for ch in text:
        for u in (ch.encode("utf-16-le")[i:i+2] for i in range(0, max(len(ch.encode("utf-16-le")), 2), 2)):
            sc = int.from_bytes(u, "little")
            if sc == 0:
                continue
            i = INPUT(type=1); i.u.ki = KEYBDINPUT(0, sc, UNICODE, 0, None); _send(i)
            j = INPUT(type=1); j.u.ki = KEYBDINPUT(0, sc, UNICODE | KEYUP, 0, None); _send(j)
        time.sleep(0.01)
    return {"typed": len(text)}

def drag(x1, y1, x2, y2, steps=24, button="left", duration=None):
    move(x1, y1)
    time.sleep(0.08)
    dn = LEFTDN if button == "left" else RIGHTDN
    up = LEFTUP if button == "left" else RIGHTUP
    _mouse(dn)
    time.sleep(0.05)
    for i in range(1, steps + 1):
        _mouse(0, int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.012)
    time.sleep(0.05)
    _mouse(up)
    return {"dragged": [[x1, y1], [x2, y2]], "button": button}

def scroll(x=None, y=None, amount=-3, horizontal=False):
    if x is not None:
        move(x, y)
    i = INPUT(type=0)
    flag = 0x0800 if not horizontal else 0x1000        # WHEEL / HWHEEL
    i.u.mi = MOUSEINPUT(0, 0, (amount * 120) & 0xFFFFFFFF, flag, 0, None)
    _send(i)
    time.sleep(0.05)
    return {"scrolled": amount, "at": [x, y], "horizontal": horizontal}

def keydown(combo):
    for p in [x.strip().lower() for x in combo.replace(" ", "").split("+")]:
        _key_vk(VK[p])
    return {"down": combo}

def keyup(combo):
    for p in [x.strip().lower() for x in combo.replace(" ", "").split("+")]:
        _key_vk(VK[p], True)
    return {"up": combo}

# ---------- OCR（Windows 原生，经隐藏 PowerShell 调用，无闪窗） ----------
def unc_path(p):
    if p.startswith("\\\\") or (len(p) > 1 and p[1] == ":"):
        return p                                        # 已经是 Windows 路径
    if not p.startswith("/"):
        raise ValueError("必须是绝对路径（WSL 或 Windows）：" + p)
    return "\\\\wsl.localhost\\Ubuntu" + p.replace("/", "\\")

def ocr(path):
    import subprocess
    ps1 = os.path.join(HERE, "ocr.ps1")
    unc = unc_path(path)
    ps = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", ps1, "-Path", unc],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000)      # CREATE_NO_WINDOW → 不闪窗
    if r.returncode != 0:
        raise RuntimeError("OCR 失败: " + (r.stderr or r.stdout)[:300])
    return json.loads(r.stdout.strip())


def _uia():
    import uiautomation as auto
    return auto

def elements(depth=3, limit=300):
    auto = _uia()
    root = auto.GetForegroundControl()
    out = []
    def walk(ctrl, d):
        if len(out) >= limit or d > depth:
            return
        try:
            r = ctrl.BoundingRectangle
            out.append({"depth": d, "type": ctrl.ControlTypeName, "name": (ctrl.Name or "")[:80],
                        "id": ctrl.AutomationId or "", "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top]})
        except Exception:
            return
        for c in ctrl.GetChildren():
            walk(c, d + 1)
    walk(root, 0)
    return {"window": root.Name, "count": len(out), "elements": out}

def invoke(name, exact=False, ctype=None, action="click"):
    auto = _uia()
    root = auto.GetForegroundControl()
    def walk(ctrl, d=0):
        if d > 6:
            return None
        try:
            nm = ctrl.Name or ""
            if (nm == name if exact else name in nm) and (not ctype or ctrl.ControlTypeName == ctype):
                return ctrl
        except Exception:
            pass
        for c in ctrl.GetChildren():
            r = walk(c, d + 1)
            if r:
                return r
        return None
    t = walk(root)
    if not t:
        return {"found": False, "error": "未找到控件: " + name}
    try:
        if action == "click":
            t.Click(simulateMove=False) if "simulateMove" in t.Click.__code__.co_varnames else t.Click()
        elif action == "focus":
            t.SetFocus()
        r = t.BoundingRectangle
        return {"found": True, "type": t.ControlTypeName, "name": t.Name,
                "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top], "action": action}
    except Exception as e:
        return {"found": True, "action_failed": str(e)}

# ---------- 分发 ----------
def dispatch(req):
    c = req.get("cmd")
    a = req.get("args") or {}
    if c == "ping":
        return {"pong": True, "pid": os.getpid()}
    if c == "shot":
        return shot(a["out"], a.get("fmt", "png"))
    if c == "windows":
        return {"count": 0, "windows": windows()}
    if c == "foreground":
        return foreground()
    if c == "focus":
        return focus(a["match"])
    if c == "move":
        return move(a["x"], a["y"])
    if c == "click":
        return click(a.get("x"), a.get("y"), a.get("button", "left"), a.get("double", False))
    if c == "key":
        return key(a["combo"])
    if c == "type":
        return type_text(a["text"])
    if c == "elements":
        return elements(a.get("depth", 3), a.get("limit", 300))
    if c == "drag":
        return drag(a["x1"], a["y1"], a["x2"], a["y2"], a.get("steps", 24), a.get("button", "left"))
    if c == "scroll":
        return scroll(a.get("x"), a.get("y"), a.get("amount", -3), a.get("horizontal", False))
    if c == "keydown":
        return keydown(a["combo"])
    if c == "keyup":
        return keyup(a["combo"])
    if c == "ocr":
        return ocr(a["path"])
    if c == "crop":                       # 从图里裁出一块（做模板用）
        import importlib, img
        importlib.reload(img)             # img.py 可能被改过 → 每次重载
        out = img.crop_unc(a["src"], a["out"], a["x"], a["y"], a["w"], a["h"])
        return out
    if c == "bmp2png":
        import importlib, img
        importlib.reload(img)
        return img.to_png_unc(a["src"], a["out"])
    if c == "findimg":                    # 模板匹配（numpy，进程内，无闪窗）
        import importlib, img
        importlib.reload(img)
        return img.find_unc(a["screen"], a["template"], a.get("top", 3), a.get("gray", False))
    if c == "invoke":
        return invoke(a["name"], a.get("exact", False), a.get("ctype"), a.get("action", "click"))
    if c == "flaui":                      # FlaUI(UIA3) 工业级后端
        import importlib, flaui
        importlib.reload(flaui)
        sub = a.get("sub")
        fn = getattr(flaui, sub, None) if sub else None
        if not fn:
            return {"error": "unknown flaui sub: %r" % sub}
        return fn(**{k: v for k, v in a.items() if k != "sub"})
    return {"error": "unknown cmd: %r" % c}

def main():
    log("main() enter, QUEUE=%r" % QUEUE)
    os.makedirs(QUEUE, exist_ok=True)
    with open(PIDF, "w") as f:
        f.write(str(os.getpid()))
    log("pid written = %s" % os.getpid())
    last_hb = 0.0
    while True:
        try:
            for f in sorted(glob.glob(os.path.join(QUEUE, "cmd-*.json"))):
                rid = os.path.basename(f)[4:-5]
                try:
                    req = json.load(open(f, encoding="utf-8"))
                except Exception:
                    try: os.remove(f)
                    except Exception: pass
                    continue
                try:
                    res = {"ok": True, "result": dispatch(req)}
                except Exception as e:
                    res = {"ok": False, "error": str(e), "tb": traceback.format_exc()[-600:]}
                try:
                    with open(os.path.join(QUEUE, "res-%s.json" % rid), "w", encoding="utf-8") as rf:
                        json.dump(res, rf, ensure_ascii=False)
                finally:
                    try: os.remove(f)
                    except Exception: pass
                if req.get("cmd") == "stop":
                    return
            now = time.time()
            if now - last_hb > 1:
                with open(HB, "w") as hf:
                    hf.write("%.0f" % now)
                last_hb = now
            time.sleep(0.03)
        except Exception:
            time.sleep(0.2)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL\n" + traceback.format_exc())
        raise
