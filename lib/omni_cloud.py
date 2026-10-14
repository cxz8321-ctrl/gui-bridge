#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui-bridge · 云 VLM 兜底（GLM-4.6V）—— 本地 Florence 描述泛/失败时的第二层
用法（WSL 侧跑）：
  python3 lib/omni_cloud.py                 # 处理 result json 里 needs_cloud 的 icon
  python3 lib/omni_cloud.py --ctx           # 同上，但带"整屏上下文 + 框选位置"一起问（v2，更准）
  python3 lib/omni_cloud.py --all           # 全部 icon 都过一遍
  python3 lib/omni_cloud.py --ground        # 整屏 grounding（本地 OCR+找图都失败时的兜底）
  python3 lib/omni_cloud.py --crop <png>    # 单张 crop 试描述
产出：把结果写回 omniparser_result.json 的 label_cloud / 云兜底元素表，并打 --json 输出到 stdout
"""
import base64, json, os, re, sys, urllib.request

RESULT = "/mnt/c/Users/Think/AppData/Local/gui-bridge-vlm/out/omniparser_result.json"
SECRETS = os.path.expanduser("~/.config/gui-bridge/secrets.json")
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6v"
PROMPT_ICON = ("这是 Windows 桌面上的一个 UI 图标/控件的放大截图（可能带少量周边留白）。"
               "用不超过 10 个汉字说明它是什么或什么功能。只回这串汉字，不要标点、不要解释。")
PROMPT_GROUND = ("这是 Windows 桌面全屏截图（3200x2000 物理像素）。请列出图上所有可点击的图标/控件，"
                 "每行格式：功能（≤8字）|中心x|中心y 。只输出这些行，不要任何解释或标题。最多 40 行。")
PROMPT_SCENE = ("这是 Windows 桌面截图。用一句话（≤40字）说明这是什么窗口/界面、当前在干什么。")
PROMPT_ICON_CTX = (
    "图1：Windows 桌面全屏截图（3200x2000 物理像素）。\n"
    "图2：从图1中框选出来并放大的一个图标/控件，它在图1中的位置是 x={x}, y={y}，宽 {w}，高 {h}（左上角为原点）。\n"
    "请结合图1的上下文（这是什么窗口、这个位置旁边有什么、它在哪个栏/哪个区域）和图2本身的形状，"
    "判断这个图标/控件是什么，用不超过 8 个汉字回答。只回这串汉字，不要标点、不要解释。"
)


def win_path(p):
    """Windows 路径 → WSL 路径（C:\a\b → /mnt/c/a/b）"""
    if not p:
        return p
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if m:
        return "/mnt/%s/%s" % (m.group(1).lower(), m.group(2).replace("\\", "/"))
    return p


def api_key():
    with open(SECRETS, encoding="utf-8") as f:
        return json.load(f)["zhipu"]["apiKey"]


def _post(parts, max_tokens=1200, timeout=180):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": parts}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + api_key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    msg = d["choices"][0]["message"]
    txt = (msg.get("content") or "").strip()
    if not txt:
        # GLM-4.6V 是推理模型：max_tokens 被 reasoning 吃完时 content 会空 → 从思维链尾部兜一个短答
        rc = (msg.get("reasoning_content") or "")
        import re as _re
        # 只认"像标签"的短词（图标/按钮/控件… 结尾），避免抓到"所以这个控件"这类思维链碎片
        cands = [c for c in _re.findall(r"[\u4e00-\u9fa5]{2,8}", rc[-400:])
                 if c.endswith(("图标", "按钮", "控件", "箭头", "菜单", "选项", "栏", "标签", "窗口", "球", "标"))]
        txt = cands[-1] if cands else ""
        if not txt:
            raise RuntimeError("空回复（finish=%s，reasoning %d 字）" % (d["choices"][0].get("finish_reason"), len(rc)))
    return txt.strip("\n 　。")


def _img(png_bytes):
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png_bytes).decode()}}


def ask(png_bytes, prompt, max_tokens=1200, timeout=180):
    return _post([_img(png_bytes), {"type": "text", "text": prompt}], max_tokens, timeout)


def ask_ctx(full_bytes, crop_bytes, box, max_tokens=1200, timeout=180):
    """整屏上下文 + 框选位置 + 放大 crop 一起问（v2：解决"光看小图猜不准"）"""
    x, y, w, h = [int(v) for v in box]
    parts = [_img(full_bytes), _img(crop_bytes),
             {"type": "text", "text": PROMPT_ICON_CTX.format(x=x, y=y, w=w, h=h)}]
    return _post(parts, max_tokens, timeout)



def main():
    args = sys.argv[1:]
    if "--crop" in args:
        p = args[args.index("--crop") + 1]
        with open(p, "rb") as f:
            print(ask(f.read(), PROMPT_ICON))
        return
    with open(RESULT, encoding="utf-8") as f:
        data = json.load(f)
    img_path = data.get("image", "")
    if "--ground" in args:
        with open(win_path(img_path), "rb") as f:
            out = ask(f.read(), PROMPT_GROUND, max_tokens=900)
        data["cloud_grounding"] = out
    if "--scene" in args:
        with open(win_path(img_path), "rb") as f:
            data["cloud_scene"] = ask(f.read(), PROMPT_SCENE, max_tokens=80)
    todo = [(i, b) for i, b in enumerate(data.get("icons", []))
            if ("--all" in args or b.get("needs_cloud")) and b.get("crop_path") and os.path.exists(win_path(b["crop_path"]))]
    use_ctx = "--ctx" in args
    only = None
    if "--only" in args:
        only = {int(v) for v in args[args.index("--only") + 1].split(",")}
    mt = 2048 if use_ctx else 1200
    full_bytes = None
    if use_ctx:
        with open(win_path(img_path), "rb") as f:
            full_bytes = f.read()
    todo = [t for t in todo if only is None or t[0] in only]
    print("需要云兜底的 icon：%d 个（模式：%s）" % (len(todo), "整屏上下文+框选" if use_ctx else "仅 crop"), file=sys.stderr)
    ok = 0
    for n, (i, b) in enumerate(todo):
        try:
            with open(win_path(b["crop_path"]), "rb") as f:
                crop = f.read()
            txt = ask_ctx(full_bytes, crop, b.get("box", [0, 0, 0, 0]), max_tokens=mt) if use_ctx \
                else ask(crop, PROMPT_ICON, max_tokens=mt)
            b["label_cloud"] = txt
            b["label_final"] = txt
            b["cloud_mode"] = "ctx" if use_ctx else "crop"
            ok += 1
            print("  [%d/%d] icon_%02d %s -> %s" % (n + 1, len(todo), i, b.get("label", "")[:34], txt), file=sys.stderr)
        except Exception as e:
            b["label_cloud"] = ""
            b["cloud_error"] = str(e)[:160]
            print("  [%d/%d] icon_%02d 云调用失败：%s" % (n + 1, len(todo), i, str(e)[:120]), file=sys.stderr)
    for b in data.get("icons", []):
        if not b.get("label_final"):
            b["label_final"] = b.get("label", "")
    data["cloud_done"] = ok
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("云兜底完成：%d/%d" % (ok, len(todo)), file=sys.stderr)
    if "--json" in args:
        print(json.dumps({"cloud_done": ok, "cloud_grounding": data.get("cloud_grounding"),
                          "icons": [{"i": i, "local": b.get("label", "")[:60], "cloud": b.get("label_cloud", "")}
                                    for i, b in enumerate(data.get("icons", []))]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
