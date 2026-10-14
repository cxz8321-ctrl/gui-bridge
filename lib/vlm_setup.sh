#!/usr/bin/env bash
# 开发模式 · 视觉解析实验（OmniParser 路线的依赖安装）
# 装在 Windows 侧独立 venv（Python 3.10），不碰系统 Python；要删直接删目录
set -uo pipefail
LOG=/home/caixingzhe/gui-bridge/tmp/vlm_setup.log
mkdir -p "$(dirname "$LOG")"
PY310=/mnt/c/Users/Think/AppData/Local/Programs/Python/Python310/python.exe
VENV_WIN='C:\Users\Think\AppData\Local\gui-bridge-vlm'
VENV_PY="$VENV_WIN\\Scripts\\python.exe"
VENV_PY_UNIX=/mnt/c/Users/Think/AppData/Local/gui-bridge-vlm/Scripts/python.exe
PROXY=http://127.0.0.1:7897

say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "== 1/4 建 venv =="
if [ ! -x "$VENV_PY_UNIX" ]; then
  "$PY310" -m venv "$VENV_WIN" >>"$LOG" 2>&1
fi
[ -x "$VENV_PY_UNIX" ] && say "venv OK: $("$VENV_PY_UNIX" -c 'import sys;print(sys.version.split()[0])')" || { say "venv 失败"; exit 1; }

say "== 2/4 升级 pip =="
WSLENV=HTTPS_PROXY:HTTP_PROXY HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY \
  "$VENV_PY_UNIX" -m pip install -q --upgrade pip >>"$LOG" 2>&1 && say "pip OK"

say "== 3/4 装 torch(CPU) —— 约 200MB，最慢的一步 =="
WSLENV=HTTPS_PROXY:HTTP_PROXY HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY \
  "$VENV_PY_UNIX" -m pip install torch --index-url https://download.pytorch.org/whl/cpu >>"$LOG" 2>&1 \
  && say "torch OK: $("$VENV_PY_UNIX" -c 'import torch;print(torch.__version__)')" || say "torch 失败（见日志）"

say "== 4/4 装 transformers / ultralytics / pillow =="
WSLENV=HTTPS_PROXY:HTTP_PROXY HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY \
  "$VENV_PY_UNIX" -m pip install -q transformers ultralytics pillow timm einops sentencepiece accelerate \
  >>"$LOG" 2>&1 && say "全部依赖 OK" || say "部分依赖失败（见日志）"

say "== 完成，各版本 =="
"$VENV_PY_UNIX" -c "
import torch, transformers, PIL
print('torch', torch.__version__, '| transformers', transformers.__version__, '| pillow', PIL.__version__)
import ultralytics; print('ultralytics', ultralytics.__version__)
" 2>&1 | tee -a "$LOG"
say "DONE"
