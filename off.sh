#!/usr/bin/env bash
# gui-bridge · 关闭：停助手、清授权
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"

python3 "$ROOT/gb.py" stop >/dev/null 2>&1 || true
# 兜底：按 pid 强杀
if [ -f "$ROOT/bridge.pid" ]; then
  pid="$(cat "$ROOT/bridge.pid" 2>/dev/null || true)"
  [ -n "$pid" ] && /mnt/c/Windows/System32/taskkill.exe /PID "$pid" /F >/dev/null 2>&1 || true
  rm -f "$ROOT/bridge.pid" "$ROOT/bridge.heartbeat"
fi
rm -f "$STATE_FILE"
audit "OFF 手动解除"
echo "🔓 已关闭：助手已停、授权已清（回到常态）"
