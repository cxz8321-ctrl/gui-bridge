#!/usr/bin/env bash
# 开发模式 · 眼睛模块：抓一张全屏截图，存到 shots/，并留痕
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"

need_armed eyes

TS="$(date +%F_%H%M%S)"
OUT="$ROOT/shots/shot_${TS}.png"
mkdir -p "$ROOT/shots"

PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
PS1="$ROOT/lib/shot.ps1"
b64="$(iconv -f utf-8 -t utf-16le "$PS1" | base64 -w0)"

# 通过环境变量把目标路径传进去（WSLENV 是 WSL→Windows 传变量的开关，必须显式声明）
WSLENV=OUT OUT="$OUT" "$PS" -NoProfile -NonInteractive -EncodedCommand "$b64" 2>/dev/null | tr -d '\000' || true

if [ -s "$OUT" ]; then
  sz=$(stat -c %s "$OUT")
  dim=$(python3 -c "import struct,sys;d=open('$OUT','rb').read(33);print(f'{struct.unpack(\">I\",d[16:20])[0]}x{struct.unpack(\">I\",d[20:24])[0]}')" 2>/dev/null || echo '?')
  echo "👁  截图完成：$OUT"
  echo "    $dim  $((sz/1024)) KB"
  audit "EYE shot=$OUT dim=$dim size=$sz"
else
  echo "❌ 截图失败（没拿到文件）"
  audit "EYE-FAIL"
  exit 1
fi
