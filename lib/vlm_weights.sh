#!/usr/bin/env bash
# gui-bridge · 下载 OmniParser 权重（图标检测 + 图标描述），走本地代理
set -uo pipefail
LOG=/home/caixingzhe/gui-bridge/tmp/vlm_weights.log
W=/mnt/c/Users/Think/AppData/Local/gui-bridge-vlm
PY="$W/Scripts/python.exe"
PROXY=http://127.0.0.1:7897
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

run(){ WSLENV=HTTPS_PROXY:HTTP_PROXY:HF_HOME HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY \
       HF_HOME='C:\Users\Think\AppData\Local\gui-bridge-vlm\hf' "$@"; }

say "== 1/3 装 huggingface_hub =="
run "$PY" -m pip install -q huggingface_hub >>"$LOG" 2>&1 && say "hub OK" || say "hub 失败"

say "== 2/3 下 OmniParser v2 权重（图标检测 YOLO + Florence 描述）=="
run "$PY" - <<'PYEOF' >>"$LOG" 2>&1
from huggingface_hub import snapshot_download
p = snapshot_download('microsoft/OmniParser-v2.0',
                      local_dir=r'C:\Users\Think\AppData\Local\gui-bridge-vlm\weights\omniparser',
                      allow_patterns=['icon_detect/*', 'icon_caption/*'])
print('OMNIPARSER_DONE', p)
PYEOF
grep -q OMNIPARSER_DONE "$LOG" && say "OmniParser 权重 OK" || say "OmniParser 权重失败（见日志）"

say "== 3/3 Flore-2 base（通用视觉描述，备用）=="
run "$PY" - <<'PYEOF' >>"$LOG" 2>&1
from huggingface_hub import snapshot_download
p = snapshot_download('microsoft/Florence-2-base',
                      local_dir=r'C:\Users\Think\AppData\Local\gui-bridge-vlm\weights\florence2',
                      allow_patterns=['*.json', '*.txt', '*.safetensors', '*.py'])
print('FLORENCE_DONE', p)
PYEOF
grep -q FLORENCE_DONE "$LOG" && say "Florence-2 OK" || say "Florence-2 失败（见日志）"
say "ALL DONE"
