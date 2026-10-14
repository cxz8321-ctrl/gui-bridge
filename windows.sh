#!/usr/bin/env bash
# gui-bridge · 窗口视野：列出当前顶层窗口（控件级"看得见"）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib/guard.sh"
need_armed windows

PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
b64="$(iconv -f utf-8 -t utf-16le "$ROOT/lib/windows.ps1" | base64 -w0)"
"$PS" -NoProfile -NonInteractive -EncodedCommand "$b64" 2>/dev/null | tr -d '\000'
audit "WINDOWS 列窗口"
