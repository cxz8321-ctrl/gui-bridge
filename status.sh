#!/usr/bin/env bash
# 开发模式 · 状态
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"

if [ ! -f "$STATE_FILE" ]; then
  echo "😴 未变身（常态）"
else
  tok="$(cat "$STATE_FILE")"
  echo "⚔️  变身中：$tok"
  [[ " $tok " == *" timed "* ]] && echo "    （限时模式，到点自动解除）" || echo "    （直到你说卸甲）"
fi
python3 "$ROOT/gb.py" status
echo "---- audit.log 最近 8 条 ----"
tail -8 "$AUDIT_LOG" 2>/dev/null || echo "(暂无)"
