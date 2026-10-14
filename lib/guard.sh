# gui-bridge · 守卫（给 sh 脚本用；gb.py 内置同款逻辑）
GUARD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="$GUARD_ROOT/state"
AUDIT_LOG="$GUARD_ROOT/audit.log"

audit() { echo "$(date '+%F %T') $*" >> "$AUDIT_LOG"; }

# 状态文件：第一个词是 eyes|hands，可带 "timed <epoch>" 后缀
need_armed() {
  local module="${1:-action}" need_hands="${2:-}"
  if [ ! -f "$STATE_FILE" ]; then
    echo "🔒 未开启：先执行 ./on.sh（$module 需要授权）" >&2
    audit "DENY $module (未开启)"; return 1
  fi
  local tok; tok="$(cat "$STATE_FILE")"
  if [[ " $tok " == *" timed "* ]]; then
    local exp; exp="$(echo "$tok" | awk '{for(i=1;i<=NF;i++) if($i=="timed") print $(i+1)}')"
    if [ -n "$exp" ] && [ "$(date +%s)" -ge "$exp" ]; then
      rm -f "$STATE_FILE"; echo "⌛ 授权已到期，自动解除" >&2
      audit "EXPIRED $module"; return 1
    fi
  fi
  if [ "$need_hands" = "hands" ] && [[ " $tok " != *" hands "* ]]; then
    echo "🔒 未授权'手'（当前只有眼睛）：需要 ./on.sh --hands" >&2
    audit "DENY $module (未授权手)"; return 1
  fi
  return 0
}
