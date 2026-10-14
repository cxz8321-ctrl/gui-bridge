#!/usr/bin/env bash
# 开发模式 · FlaUI 命令行（直接吐 JSON）
# 用法：
#   ./flaui.sh windows
#   ./flaui.sh tree    -Window '文件资源管理器' -Depth 3 -Limit 60
#   ./flaui.sh find    -Name '查看' -Exact
#   ./flaui.sh click   -Name '最小化'
#   ./flaui.sh settext -Name '搜索框' -Value 'hello'
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
UNC='\\wsl.localhost\Ubuntu'"${ROOT//\//\\}"'\flaui\flaui.ps1'
exec "$PS" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$UNC" "$@"
