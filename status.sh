#!/usr/bin/env bash
# gui-bridge · 状态
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"

if [ ! -f "$STATE_FILE" ]; then
  echo "😴 未开启（常态）"
else
  tok="$(cat "$STATE_FILE")"
  echo "🟢 已开启：$tok"
  [[ " $tok " == *" timed "* ]] && echo "    （限时模式，到点自动解除）" || echo "    （直到手动关闭）"
fi
python3 "$ROOT/gb.py" status
echo "---- audit.log 最近 8 条 ----"
tail -8 "$AUDIT_LOG" 2>/dev/null || echo "(暂无)"
