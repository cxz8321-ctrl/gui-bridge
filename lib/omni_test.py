#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui-bridge · 视觉解析实验（OmniParser 路线）v2
改进（2026-09-13 18:00）：
  ① 放大 crop：带上下文留白裁剪 + LANCZOS 放大（默认 3x，上限 768px）+ 提高输出 token
     并落盘每个 icon 的 crop 到 out/crops/，供云 VLM 兜底复用
  ② 泛描述检测：Florence 输出"a simple shape / not discernible / symbol"这类空泛描述时打 needs_cloud 标记
运行（Windows 侧 venv）："%LOCALAPPDATA%\\gui-bridge-vlm\\Scripts\\python.exe" omni_test.py <img> [--limit N] [--scale 3] [--pad 0.3]
"""
import json, os, re, subprocess, sys, time

W = r"C:\Users\Think\AppData\Local\gui-bridge-vlm"
OUT = os.path.join(W, "out")
CROPS = os.path.join(OUT, "crops")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CROPS, exist_ok=True)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.log")

def arg(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

IMG = next((a for a in sys.argv[1:] if not a.startswith("--") and os.path.splitext(a)[1].lower() in (".png", ".jpg", ".jpeg", ".bmp")),
           os.path.join(OUT, "screen.png"))
LIMIT = int(arg("--limit", "24"))
SCALE = float(arg("--scale", "3"))
PAD = float(arg("--pad", "0.30"))          # 上下文留白比例
MAXSIDE = int(arg("--maxside", "768"))     # 放大后的上限边长

def log(m):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

GENERIC = re.compile(r"simple|basic|generic|symbol|shape|not discernible|unclear|logo|sticker|"
                     r"appears to be|possibly|or element|abstract|unidentified", re.I)

def is_generic(label, w, h):
    """泛描述启发式：命中空泛词 / 描述过短 / icon 本身太小 / 重复词"""
    if not label:
        return True
    t = label.strip().lower()
    if GENERIC.search(t):
        return True
    if len(t) < 18:
        return True
    if w * h < 4000:                        # 面积 < 63×63
        return True
    if re.search(r"\b(\w{4,})\b.*\b\1\b", t):   # 同一个词重复出现（Florence 常见退化）
        return True
    return False

t_all = time.time()
from PIL import Image, ImageDraw

log("== 1/4 图标检测（YOLO icon_detect）==")
from ultralytics import YOLO
t0 = time.time()
yolo = YOLO(os.path.join(W, "weights", "omniparser", "icon_detect", "model.pt"))
res = yolo(IMG, conf=0.3, verbose=False)[0]
raw = []
for b in res.boxes:
    x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
    raw.append({"box": [x1, y1, x2 - x1, y2 - y1], "conf": round(float(b.conf[0]), 3)})
log("检出图标/元素 %d 个，耗时 %.1fs" % (len(raw), time.time() - t0))

log("== 2/4 图标语义（Florence-2 描述 · 放大 crop %.1fx / 留白 %.0f%%）==" % (SCALE, PAD * 100))
t0 = time.time()
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import torch
ICON_DIR = os.path.join(W, "weights", "omniparser", "icon_caption")
img = Image.open(IMG).convert("RGB")
IW, IH = img.size
proc = model = None
try:
    sys.path.insert(0, ICON_DIR)
    from processing_florence2 import Florence2Processor
    proc = Florence2Processor.from_pretrained(ICON_DIR, local_files_only=True)
except Exception as e:
    log("  本地处理器直载失败，回退 AutoProcessor：%s" % str(e)[:120])
    try:
        from transformers import AutoProcessor
        proc = AutoProcessor.from_pretrained(ICON_DIR, trust_remote_code=True, local_files_only=True)
    except Exception as e2:
        proc = None
        log("!! 处理器加载失败：%s" % str(e2)[:160])
try:
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(ICON_DIR, trust_remote_code=True,
                                                 local_files_only=True, torch_dtype=torch.float32)
    model.eval()
    log("  Florence-2 就绪（处理器 %s）" % type(proc).__name__)
except Exception as e:
    log("!! Florence 模型加载失败，跳过语义标注：%s" % str(e)[:200])
    model = None

boxes = sorted(raw, key=lambda b: -b["conf"])[:LIMIT]

def make_crop(b):
    """带留白裁剪 → LANCZOS 放大（长边不超 MAXSIDE）；返回 (PIL图, 裁剪矩形)"""
    x, y, w, h = b["box"]
    px, py = int(w * PAD), int(h * PAD)
    cx0, cy0 = max(0, x - px), max(0, y - py)
    cx1, cy1 = min(IW, x + w + px), min(IH, y + h + py)
    crop = img.crop((cx0, cy0, cx1, cy1))
    cw, ch = crop.size
    scale = SCALE
    if max(cw, ch) * scale > MAXSIDE:
        scale = max(1.0, MAXSIDE / float(max(cw, ch)))
    if scale != 1.0:
        crop = crop.resize((max(1, int(cw * scale)), max(1, int(ch * scale))), Image.LANCZOS)
    return crop, (cx0, cy0, cx1, cy1)

for i, b in enumerate(boxes):
    x, y, w, h = b["box"]
    crop, rect = make_crop(b)
    b["crop_rect"] = list(rect)
    b["crop_size"] = list(crop.size)
    cp = os.path.join(CROPS, "icon_%02d.png" % i)
    try:
        crop.save(cp)
        b["crop_path"] = cp
    except Exception as e:
        log("  !! crop 落盘失败 %s: %s" % (cp, e))
    if model is None or proc is None:
        b["label"] = ""
        b["needs_cloud"] = True
        continue
    try:
        inp = proc(text="<MORE_DETAILED_CAPTION>", images=crop, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=64, num_beams=1)
        cap = proc.batch_decode(out, skip_special_tokens=True)[0].replace("<MORE_DETAILED_CAPTION>", "").strip()
        cap = re.sub(r"\s+", " ", cap)
    except Exception as e:
        cap = "描述失败: %s" % str(e)[:80]
    b["label"] = cap
    b["needs_cloud"] = is_generic(cap, w, h)
    if i % 6 == 0:
        log("  ...%d/%d（crop %dx%d → %dx%d，needs_cloud=%s）" % (i + 1, len(boxes), w, h, crop.size[0], crop.size[1], b["needs_cloud"]))
n_cloud = sum(1 for b in boxes if b.get("needs_cloud"))
log("图标描述完成：%d 个，其中 %d 个标为 needs_cloud，耗时 %.1fs" % (len(boxes), n_cloud, time.time() - t0))

log("== 3/4 文字（Windows 原生 OCR）==")
t0 = time.time()
lines = []
try:
    ps = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    ps1 = r"\\wsl.localhost\Ubuntu\home\caixingzhe\gui-bridge\lib\ocr.ps1"
    r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1, "-Path", IMG],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000)
    if r.returncode == 0:
        lines = json.loads(r.stdout.strip())["lines"]
        log("OCR 行数 %d，耗时 %.1fs" % (len(lines), time.time() - t0))
    else:
        log("OCR 失败: " + (r.stderr or r.stdout)[:150])
except Exception as e:
    log("OCR 异常: %s" % e)

log("== 4/4 输出 ==")
d = ImageDraw.Draw(img)
for b in boxes:
    x, y, w, h = b["box"]
    d.rectangle([x, y, x + w, y + h], outline=(255, 60, 60), width=3)
    tag = str(b["label"])[:26] + (" *云" if b.get("needs_cloud") else "")
    d.text((x + 2, max(0, y - 14)), tag, fill=(255, 255, 0))
for ln in lines:
    x, y, w, h = ln["rect"]
    d.rectangle([x, y, x + w, y + h], outline=(60, 160, 255), width=2)
overlay = os.path.join(OUT, "omniparser_overlay.png")
img.save(overlay)
data = {"image": IMG, "icons": boxes, "text_lines": [{"t": l["text"], "rect": l["rect"]} for l in lines],
        "overlay": overlay, "params": {"scale": SCALE, "pad": PAD, "maxside": MAXSIDE, "limit": LIMIT},
        "needs_cloud": n_cloud, "total_seconds": round(time.time() - t_all, 1)}
outj = os.path.join(OUT, "omniparser_result.json")
with open(outj, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
log("完成：%d 图标 + %d 文本行，needs_cloud %d，总耗时 %.1fs" % (len(boxes), len(lines), n_cloud, time.time() - t_all))
log("结果: %s" % outj)
log("标注图: %s" % overlay)
log("DONE")
