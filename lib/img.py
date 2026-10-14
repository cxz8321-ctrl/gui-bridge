#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开发模式 · 阶段三图像工具（只需 numpy）：模板匹配 / 裁剪 / BMP↔PNG

用法：
  img.py info  <图>
  img.py crop  <入> <出> x y w h
  img.py png   <入.bmp> <出.png>
  img.py find  <屏幕图> <模板图> [--top 3] [--gray]
"""
import json, os, struct, subprocess, sys, zlib

import numpy as np


# ---------- BMP 读写（numpy 直接可用，无需解码库） ----------
def read_bmp(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"BM":
        raise ValueError("不是 BMP: " + path)
    off = struct.unpack_from("<I", data, 10)[0]
    w, h, planes, bits, comp = struct.unpack_from("<iiHHI", data, 18)
    top_down = h < 0
    h = abs(h)
    if comp != 0:
        raise ValueError("只支持 BI_RGB 的 BMP")
    bpp = bits // 8
    stride = w * bpp
    a = np.frombuffer(data, dtype=np.uint8, count=stride * h, offset=off).reshape(h, w, bpp)
    if not top_down:
        a = a[::-1]
    if bpp == 4:
        bgr = a[:, :, :3]
    elif bpp == 3:
        bgr = a
    else:
        raise ValueError("只支持 24/32bpp")
    return bgr[:, :, ::-1].copy()          # BGR → RGB


def ensure_bmp(path, workdir="/tmp"):
    """非 BMP（如 PNG）需要先转 BMP。Windows 侧没 ffmpeg → 明确报错，由调用方先转。"""
    with open(path, "rb") as f:
        if f.read(2) == b"BM":
            return path
    if os.path.exists("/usr/bin/ffmpeg"):
        out = os.path.join(workdir, "gb_conv_%d.bmp" % (abs(hash(path)) % 10**8))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, out], check=True)
        return out
    raise ValueError("需要 BMP 输入（Windows 侧无 ffmpeg）：%s" % path)


def write_png(path, rgb):
    h, w, _ = rgb.shape
    raw = bytearray()
    for y in range(h):
        raw += b"\x00" + rgb[y].tobytes()
    def ch(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n"
    data += ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += ch(b"IDAT", zlib.compress(bytes(raw), 6))
    data += ch(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


# ---------- 归一化互相关（FFT 加速，向量化，无循环） ----------
def ncc(screen, tpl):
    I = screen.astype(np.float64)
    T = tpl.astype(np.float64)
    H, W = I.shape
    th, tw = T.shape
    if th > H or tw > W:
        raise ValueError("模板比屏幕大")
    oh, ow = H - th + 1, W - tw + 1
    n = th * tw

    # 局部和 / 局部平方和（积分图，向量化）
    ii = np.cumsum(np.cumsum(I, 0), 1)
    ii2 = np.cumsum(np.cumsum(I * I, 0), 1)
    def win(ii_):
        A = ii_[th - 1:H, tw - 1:W]
        B = np.zeros_like(A); B[1:, :] = ii_[0:oh - 1, tw - 1:W]
        C = np.zeros_like(A); C[:, 1:] = ii_[th - 1:H, 0:ow - 1]
        D = np.zeros_like(A); D[1:, 1:] = ii_[0:oh - 1, 0:ow - 1]
        return A - B - C + D
    S = win(ii)
    S2 = win(ii2)

    # 互相关（FFT，零填充避免环绕）：cc[y,x] = Σ I[y:y+th, x:x+tw] * T
    fh, fw = H + th, W + tw
    corr = np.fft.irfft2(np.fft.rfft2(I, (fh, fw)) * np.conj(np.fft.rfft2(T, (fh, fw))), (fh, fw))
    num0 = corr[0:oh, 0:ow]

    mT = T.mean()
    T2 = float((T * T).sum())
    mloc = S / n
    num = num0 - n * mloc * mT
    den = np.sqrt(np.maximum(S2 - n * mloc * mloc, 0) * max(T2 - n * mT * mT, 0))
    score = np.where(den > 1e-9, num / np.maximum(den, 1e-9), 0.0)
    return score


def find(screen_path, tpl_path, top=3, use_gray=False):
    scr = read_bmp(ensure_bmp(screen_path))
    tpl = read_bmp(ensure_bmp(tpl_path))
    if use_gray:
        scr = scr @ np.array([0.299, 0.587, 0.114])
        tpl = tpl @ np.array([0.299, 0.587, 0.114])
        scr = scr.astype(np.float64); tpl = tpl.astype(np.float64)
    else:
        scr = scr.astype(np.float64).mean(2)
        tpl = tpl.astype(np.float64).mean(2)
    sc = ncc(scr, tpl)
    th, tw = tpl.shape
    hits = []
    s = sc.copy()
    for _ in range(top):
        idx = int(np.argmax(s))
        y, x = divmod(idx, s.shape[1])
        hits.append({"x": int(x), "y": int(y), "w": int(tw), "h": int(th),
                     "cx": int(x + tw // 2), "cy": int(y + th // 2),
                     "score": round(float(s[y, x]), 4)})
        y0, y1 = max(0, y - th // 2), min(s.shape[0], y + th // 2 + 1)
        x0, x1 = max(0, x - tw // 2), min(s.shape[1], x + tw // 2 + 1)
        s[y0:y1, x0:x1] = -1
    return {"template": [int(tw), int(th)], "screen": [int(scr.shape[1]), int(scr.shape[0])], "hits": hits}


WSL_PREFIX = "\\\\wsl.localhost\\Ubuntu"


def unc(p):
    """WSL 路径 → Windows UNC（helper 是 Windows 进程，读不到 /home/...）"""
    return WSL_PREFIX + p.replace("/", "\\") if p.startswith("/") else p


def find_unc(screen, tpl, top=3, gray=False):
    return find(unc(screen), unc(tpl), top, gray)


def crop_unc(src, out, x, y, w, h):
    img = read_bmp(unc(src))
    c = img[y:y + h, x:x + w]
    write_png(unc(out), c)
    return {"out": out, "at": [x, y], "size": [int(c.shape[1]), int(c.shape[0])]}


def to_png_unc(src, out):
    write_png(unc(out), read_bmp(unc(src)))
    return {"out": out}


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "info":
        img = read_bmp(ensure_bmp(a[1]))
        print(json.dumps({"size": [int(img.shape[1]), int(img.shape[0])]}))
    elif cmd == "crop":
        img = read_bmp(ensure_bmp(a[1]))
        x, y, w, h = map(int, a[3:7])
        out = img[y:y + h, x:x + w]
        write_png(a[2], out)
        print(json.dumps({"out": a[2], "size": [int(out.shape[1]), int(out.shape[0])]}))
    elif cmd == "png":
        write_png(a[2], read_bmp(ensure_bmp(a[1])))
        print(json.dumps({"out": a[2]}))
    elif cmd == "find":
        top = 3
        if "--top" in a:
            top = int(a[a.index("--top") + 1])
        print(json.dumps(find(a[1], a[2], top, "--gray" in a), ensure_ascii=False))
    else:
        print("未知子命令: " + cmd, file=sys.stderr); sys.exit(1)


if __name__ == "__main__":
    main()
