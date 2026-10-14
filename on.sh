#!/usr/bin/env bash
# gui-bridge · 召唤：启用 GUI 桥（默认 = 直到你喊卸才卸；不设自动到期）
# 用法：./on.sh [--eyes-only] [--hands] [--timed 分钟]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"

MODE="hands"      # 阶段二后默认带手；--eyes-only 可退化成只看
TIMED=""
args=("$@")
for ((i=0;i<${#args[@]};i++)); do
  case "${args[$i]}" in
    --eyes-only) MODE="eyes" ;;
    --hands) MODE="hands" ;;
    --timed) TIMED="${args[$((i+1))]:-}" ;;
  esac
done

if [ -n "$TIMED" ]; then
  echo "$MODE timed $(( $(date +%s) + TIMED*60 ))" > "$STATE_FILE"
  audit "ON 授权=$MODE 限时=${TIMED}min 到期=$(date -d "+${TIMED} minutes" '+%F %T')"
  echo "⚔️  开启（$MODE）· 限时 ${TIMED} 分钟"
else
  echo "$MODE" > "$STATE_FILE"
  audit "ON 授权=$MODE 直到手动解除"
  echo "⚔️  开启（$MODE）· 直到你说关闭（./off.sh）"
fi

echo "    模式：$([ "$MODE" = hands ] && echo '眼睛 + 手（看 + 点/输入）' || echo '眼睛 only（只看不动）')"
python3 "$ROOT/gb.py" start >/dev/null
echo "    助手：$(cat "$ROOT/bridge.pid" 2>/dev/null | sed 's/^/pid /')  (pythonw 常驻，零闪窗)"
echo "    留痕：$AUDIT_LOG"
