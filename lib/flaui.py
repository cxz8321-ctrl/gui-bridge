# Flaui 桥（开发模式 · 工业级 UIA）
# 经隐藏 PowerShell 调 flaui/flaui.ps1，返回 dict。无闪窗（CREATE_NO_WINDOW）。
import os, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(os.path.dirname(HERE), "flaui", "flaui.ps1")
if os.name == "nt":                                  # 在 Windows 上跑（bridge.py 的运行环境）
    _PS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                       "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
else:                                                # 在 WSL 里跑（调试用；走 interop）
    import shutil
    _PS = (shutil.which("powershell.exe")
           or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")


def unc(p):
    """WSL 绝对路径 → PowerShell 可读的 UNC 路径"""
    if p.startswith("\\\\") or (len(p) > 1 and p[1] == ":"):
        return p
    return "\\\\wsl.localhost\\Ubuntu" + p.replace("/", "\\")


def run(cmd, **kw):
    args = [_PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", unc(PS1), "-Cmd", cmd]
    for k, v in kw.items():
        if v is True:
            args.append("-" + k)
        elif v is False or v is None:
            continue
        else:
            args += ["-" + k, str(v)]
    cf = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW（仅 Windows 有效）
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=cf)
    lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    if not lines:
        raise RuntimeError("flaui 无输出: " + (r.stderr or "")[:300])
    try:
        return json.loads(lines[-1])
    except Exception:
        raise RuntimeError("flaui 输出非 JSON: " + lines[-1][:300] + " | err=" + (r.stderr or "")[:200])


# ---- 对外操作（与 bridge.py 的 cmd=flaui 子命令一一对应） ----
def windows():
    return run("windows")


def tree(window=None, depth=4, limit=400):
    return run("tree", Window=window, Depth=depth, Limit=limit)


def find(name, exact=False, type=None, window=None):
    return run("find", Name=name, Exact=exact, Type=type, Window=window)


def click(name, exact=False, window=None):
    return run("click", Name=name, Exact=exact, Window=window)


def settext(name, value, window=None):
    return run("settext", Name=name, Value=value, Window=window)


def text(name, window=None):
    return run("text", Name=name, Window=window)


def focus(name, window=None):
    return run("focus", Name=name, Window=window)


def focuswin(window):
    return run("focuswin", Window=window)


if __name__ == "__main__":
    import sys
    fn = sys.argv[1]
    kw = {}
    for a in sys.argv[2:]:
        k, _, v = a.partition("=")
        kw[k] = v
    print(json.dumps(globals()[fn](**kw), ensure_ascii=False, indent=2))
