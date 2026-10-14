#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui-bridge · WSL 侧客户端：和 Windows 常驻助手对话（文件队列）

用法：
  gb.py start | stop | status
  gb.py shot                     抓屏 → shots/
  gb.py windows                  顶层窗口
  gb.py fg                       前台窗口
  gb.py focus "标题片段"
  gb.py elements [depth]         前台窗口的 UIA 元素树（结构化视野）
  gb.py invoke "按钮名" [--exact] [--ctype Button]
  gb.py click X Y [--right] [--double]
  gb.py move X Y
  gb.py drag X1 Y1 X2 Y2        拖拽
  gb.py scroll N [x y]          滚轮（正数向下）
  gb.py keydown/keyup "ctrl"    按住/松开
  gb.py type "文字"
  gb.py key "ctrl+s"
  gb.py shot [--bmp]            抓屏（--bmp 给图像匹配用）
  gb.py ocr [图]                识别文字（Windows 原生，中文）
  gb.py findtext "文字"         在屏幕上找文字 → 坐标（阶段三·兜底）
  gb.py clicktext "文字"        找到文字并点它
  gb.py findimg 模板图          模板匹配找图（numpy，进程内）
  gb.py clickimg 模板图         找到图并点它
  gb.py crop <屏幕图> <出.png> x y w h   裁一块当模板
"""
import glob, json, os, subprocess, sys, time, uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue")
STATE = os.path.join(ROOT, "state")
HB = os.path.join(ROOT, "bridge.heartbeat")
PIDF = os.path.join(ROOT, "bridge.pid")
AUDIT = os.path.join(ROOT, "audit.log")
MTIME = os.path.join(ROOT, "bridge.mtime")
TMP = os.path.join(ROOT, "tmp")
PYW = "/mnt/c/Users/Think/AppData/Local/Programs/Python/Python314/pythonw.exe"
UNC_SCRIPT = "\\\\wsl.localhost\\Ubuntu" + os.path.join(ROOT, "lib", "bridge.py").replace("/", "\\")

def audit(msg):
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%F %T"), msg))

def die(msg, code=1):
    print("🔒 " + msg, file=sys.stderr)
    audit("DENY " + msg)
    sys.exit(code)

def armed(need_hands=False):
    if not os.path.exists(STATE):
        die("未开启：先跑 ./on.sh")
    tok = open(STATE).read().split()
    if "timed" in tok:
        i = tok.index("timed")
        if time.time() >= float(tok[i + 1]):
            os.remove(STATE); die("授权已到期，已自动解除")
    if need_hands and "hands" not in tok:
        die("当前只授权了眼睛（未授权手）：需要 ./on.sh --hands")
    return tok

def alive():
    try:
        return (time.time() - float(open(HB).read().strip())) < 5
    except Exception:
        return False

def _kill_helper():
    if os.path.exists(PIDF):
        try:
            pid = open(PIDF).read().strip()
            if pid:
                subprocess.run(["/mnt/c/Windows/System32/taskkill.exe", "/PID", pid, "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass
    for f in (PIDF, HB):
        try: os.remove(f)
        except Exception: pass

def _wait_res(rid, timeout):
    """等结果文件出现并返回内容（不再重试发送，避免非幂等动作重复执行）"""
    rpath = os.path.join(QUEUE, "res-%s.json" % rid)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(rpath):
            try:
                res = json.load(open(rpath, encoding="utf-8"))
            except Exception:
                time.sleep(0.05); continue
            try: os.remove(rpath)
            except Exception: pass
            return res
        time.sleep(0.03)
    return None

def _push(cmd, args=None):
    rid = "%d-%s" % (int(time.time() * 1000), uuid.uuid4().hex[:6])
    with open(os.path.join(QUEUE, "cmd-%s.json" % rid), "w", encoding="utf-8") as f:
        json.dump({"id": rid, "cmd": cmd, "args": args or {}}, f, ensure_ascii=False)
    return rid

def start_helper():
    """确保助手真的活着：心跳 + ping 握手机验；假活或代码变过则重启"""
    os.makedirs(QUEUE, exist_ok=True)
    src = os.path.join(ROOT, "lib", "bridge.py")
    cur_mt = "%.0f" % os.path.getmtime(src)
    old_mt = open(MTIME).read().strip() if os.path.exists(MTIME) else ""
    if alive() and cur_mt == old_mt:
        r = _wait_res(_push("ping"), 3)
        if r and r.get("ok"):
            return True
        _kill_helper()                     # 假活：心跳陈旧/进程僵死 → 重启
    elif alive():
        _kill_helper()                     # 代码更新过 → 重启换新逻辑
    for f in glob.glob(os.path.join(QUEUE, "cmd-*.json")):
        try: os.remove(f)
        except Exception: pass
    subprocess.Popen([PYW, UNC_SCRIPT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 20:           # 最多等 20s，用 ping 确认真的能干活
        if os.path.exists(HB):
            r = _wait_res(_push("ping"), 2)
            if r and r.get("ok"):
                with open(MTIME, "w") as f:
                    f.write(cur_mt)
                audit("HELPER 启动 pid=%s" % open(PIDF).read().strip())
                return True
        time.sleep(0.15)
    return False

def call(cmd, args=None, timeout=40):
    if not start_helper():
        die("助手启动失败（心跳/ping 均无响应）")
    res = _wait_res(_push(cmd, args), timeout)
    if res is None:
        die("超时：%s 无响应（已发出，未收到结果；未重试以免重复执行）" % cmd)
    if not res.get("ok"):
        print("❌ " + str(res.get("error")), file=sys.stderr)
        print(res.get("tb", ""), file=sys.stderr)
        audit("FAIL %s %s" % (cmd, res.get("error")))
        sys.exit(2)
    return res["result"]

def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__); return
    sub, rest = argv[0], argv[1:]
    flags = {a for a in rest if a.startswith("--")}
    pos = [a for a in rest if not a.startswith("--")]

    if sub == "start":
        armed()
        ok = start_helper()
        if ok:
            print("✅ 助手就绪 pid=%s" % open(PIDF).read().strip())
        else:
            print("❌ 助手启动失败", file=sys.stderr)
        sys.exit(0 if ok else 1)
    if sub == "stop":
        if alive():
            _wait_res(_push("stop"), 5)
        _kill_helper()
        audit("HELPER 停止")
        print("🔓 助手已停止（pid/心跳已清）")
        return
    if sub == "status":
        if alive():
            r = _wait_res(_push("ping"), 2)
            ok = bool(r and r.get("ok"))
            print("助手：🟢 运行中 pid=%s%s" % (open(PIDF).read().strip() if os.path.exists(PIDF) else "?",
                                              "" if ok else " ⚠️ 心跳在但 ping 无响应"))
        else:
            print("助手：⚪ 未运行")
        return

    hands = sub in ("click", "move", "type", "key", "invoke", "drag", "scroll",
                    "keydown", "keyup", "clicktext", "clickimg")
    armed(need_hands=hands)

    def bmp_shot():
        os.makedirs(TMP, exist_ok=True)
        p = os.path.join(TMP, "screen.bmp")
        call("shot", {"out": p, "fmt": "bmp"})
        return p

    def ocr_on(path):
        return call("ocr", {"path": path}, timeout=90)

    def locate(text, path=None):
        """在屏幕上按文字找坐标：先整行匹配，再单词匹配（比较时忽略空格）"""
        p = path or bmp_shot()
        r = ocr_on(p)
        norm = lambda s: (s or "").replace(" ", "").lower()
        q = norm(text)
        cand = []
        for ln in r["lines"]:
            if q in norm(ln["text"]):
                cand.append(("line", ln["text"], ln["rect"]))
            for wd in (ln.get("words") or []):
                if q in norm(wd["t"]):
                    cand.append(("word", wd["t"], [wd["x"], wd["y"], wd["w"], wd["h"]]))
        cand.sort(key=lambda c: 0 if c[0] == "word" else 1)     # 单词级更精确
        if not cand:
            return {"found": False, "text": text, "lines": len(r["lines"])}
        kind, hit, rect = cand[0]
        x, y, w, h = rect
        return {"found": True, "text": text, "match": hit, "kind": kind, "rect": rect,
                "cx": x + w // 2, "cy": y + h // 2, "candidates": len(cand),
                "shot": p}

    if sub == "shot":
        os.makedirs(os.path.join(ROOT, "shots"), exist_ok=True)
        ts = time.strftime("%F_%H%M%S")
        fmt = "bmp" if "--bmp" in flags else "png"
        out = os.path.join(ROOT, "shots", "shot_%s.%s" % (ts, fmt))
        r = call("shot", {"out": out, "fmt": fmt})
        print("👁  截图 %s  (%dx%d, %d KB)" % (r["path"], r["w"], r["h"], r["bytes"] // 1024))
    elif sub == "ocr":
        p = os.path.abspath(pos[0]) if pos else bmp_shot()
        r = ocr_on(p)
        print("识别 %dx%d，%d 行" % (r["width"], r["height"], len(r["lines"])))
        for ln in r["lines"]:
            x, y, w, h = ln["rect"]
            print("  (%4d,%4d) %4dx%-4d  %s" % (x, y, w, h, ln["text"]))
    elif sub == "findtext":
        print(json.dumps(locate(pos[0]), ensure_ascii=False))
    elif sub == "clicktext":
        loc = locate(pos[0])
        if not loc.get("found"):
            print(json.dumps(loc, ensure_ascii=False)); sys.exit(3)
        call("click", {"x": loc["cx"], "y": loc["cy"], "button": "left"})
        print("🎯 已点击「%s」→ (%d,%d)  [%s 匹配]" % (pos[0], loc["cx"], loc["cy"], loc["kind"]))
    elif sub in ("findimg", "clickimg"):
        scr = bmp_shot()
        tpl = os.path.abspath(pos[0])
        if not tpl.lower().endswith(".bmp"):          # PNG 模板先转 BMP（WSL 有 ffmpeg）
            os.makedirs(TMP, exist_ok=True)
            tpb = os.path.join(TMP, "tpl.bmp")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tpl, tpb], check=True)
            tpl = tpb
        res = call("findimg", {"screen": scr, "template": tpl, "top": 3})
        print(json.dumps(res, ensure_ascii=False))
        if sub == "clickimg" and res["hits"]:
            h = res["hits"][0]
            call("click", {"x": h["cx"], "y": h["cy"], "button": "left"})
            print("🎯 已点击最佳匹配 → (%d,%d)  score=%.3f" % (h["cx"], h["cy"], h["score"]))
    elif sub == "crop":
        print(json.dumps(call("crop", {"src": os.path.abspath(pos[0]), "out": os.path.abspath(pos[1]), "x": int(pos[2]),
                                       "y": int(pos[3]), "w": int(pos[4]), "h": int(pos[5])}),
                         ensure_ascii=False))
    elif sub == "windows":
        r = call("windows")
        for w in sorted(r["windows"], key=lambda x: x["exe"]):
            x, y, ww, hh = w["rect"]
            tag = " [最小化]" if w["minimized"] else ""
            print("%-18s pid %-7d (%d,%d) %dx%d%s  %s" % (w["exe"], w["pid"], x, y, ww, hh, tag, w["title"]))
        print("TOTAL=%d" % r["count"] if "count" in r else "TOTAL=%d" % len(r["windows"]))
    elif sub == "fg":
        r = call("foreground")
        print(json.dumps(r, ensure_ascii=False))
    elif sub == "focus":
        print(json.dumps(call("focus", {"match": pos[0]}), ensure_ascii=False))
    elif sub == "elements":
        d = int(pos[0]) if pos else 3
        r = call("elements", {"depth": d})
        print("窗口: %s  元素 %d 个" % (r["window"], r["count"]))
        for e in r["elements"]:
            print("  %s%s [%s] id=%s rect=%s" % ("  " * e["depth"], e["type"],
                  (e["name"] or "-")[:60], e["id"] or "-", e["rect"]))
    elif sub == "invoke":
        args = {"name": pos[0], "exact": "--exact" in flags, "ctype": None, "action": "click"}
        for f in flags:
            if f.startswith("--ctype="):
                args["ctype"] = f.split("=", 1)[1]
        print(json.dumps(call("invoke", args), ensure_ascii=False))
    elif sub == "click":
        print(json.dumps(call("click", {"x": int(pos[0]), "y": int(pos[1]),
                                        "button": "right" if "--right" in flags else "left",
                                        "double": "--double" in flags}), ensure_ascii=False))
    elif sub == "move":
        print(json.dumps(call("move", {"x": int(pos[0]), "y": int(pos[1])}), ensure_ascii=False))
    elif sub == "type":
        print(json.dumps(call("type", {"text": pos[0]}), ensure_ascii=False))
    elif sub == "key":
        print(json.dumps(call("key", {"combo": pos[0]}), ensure_ascii=False))
    elif sub == "drag":
        print(json.dumps(call("drag", {"x1": int(pos[0]), "y1": int(pos[1]),
                                       "x2": int(pos[2]), "y2": int(pos[3])}), ensure_ascii=False))
    elif sub == "scroll":
        args = {"amount": int(pos[0])}
        if len(pos) >= 3:
            args["x"], args["y"] = int(pos[1]), int(pos[2])
        if "--horizontal" in flags:
            args["horizontal"] = True
        print(json.dumps(call("scroll", args), ensure_ascii=False))
    elif sub in ("keydown", "keyup"):
        print(json.dumps(call(sub, {"combo": pos[0]}), ensure_ascii=False))
    else:
        print("未知子命令: " + sub, file=sys.stderr); sys.exit(1)
    audit("OK %s %s" % (sub, " ".join(rest)))

if __name__ == "__main__":
    main()
