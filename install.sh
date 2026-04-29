#!/usr/bin/env bash
set -euo pipefail

# install.sh — bootstrap tg-monitor (macOS menu bar Telegram @ watcher)
#
# Usage:
#   ./install.sh             install / re-install
#   ./install.sh --uninstall remove LaunchAgent and (with confirmation) data
#
# api_id / api_hash 在安装时交互输入；也可预先导出环境变量跳过提示：
#   export TG_MONITOR_API_ID=12345678
#   export TG_MONITOR_API_HASH=abcdef0123456789abcdef0123456789

APP_NAME="TGMonitor"
LABEL="com.tgmonitor.agent"
DATA_DIR="$HOME/Library/Application Support/$APP_NAME"
LOG_DIR="$HOME/Library/Logs/$APP_NAME"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/${LABEL}.plist"
VENV_DIR="$DATA_DIR/.venv"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
info()  { printf '  %s\n' "$*"; }

require_macos() {
  if [[ "$(uname)" != "Darwin" ]]; then
    red "tg-monitor 仅支持 macOS。"
    exit 1
  fi
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  info "未检测到 uv,准备安装(astral.sh/uv)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  if ! command -v uv >/dev/null 2>&1; then
    # uv installer typically drops it in $HOME/.local/bin
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if ! command -v uv >/dev/null 2>&1; then
    red "uv 安装失败,请手动安装后重跑。"
    exit 1
  fi
}

prompt_creds() {
  # 优先使用环境变量（方便自动化部署）
  if [[ -n "${TG_MONITOR_API_ID:-}" && -n "${TG_MONITOR_API_HASH:-}" ]]; then
    API_ID="$TG_MONITOR_API_ID"
    API_HASH="$TG_MONITOR_API_HASH"
    info "已从环境变量读取 API_ID / API_HASH。"
    return
  fi

  # 若 config.json 已有凭据，询问是否沿用
  local cfg="$DATA_DIR/config.json"
  if [[ -f "$cfg" ]]; then
    local saved_id saved_hash
    saved_id=$(python3 -c "import json; d=json.load(open('$cfg')); print(d.get('api_id',''))" 2>/dev/null || true)
    saved_hash=$(python3 -c "import json; d=json.load(open('$cfg')); print(d.get('api_hash',''))" 2>/dev/null || true)
    if [[ -n "$saved_id" && "$saved_id" != "0" && -n "$saved_hash" ]]; then
      printf '\n已检测到已保存的凭据 (api_id=%s)。\n' "$saved_id"
      read -r -p "直接沿用已保存的凭据? [Y/n] " yn
      if [[ ! "$yn" =~ ^[Nn]$ ]]; then
        API_ID="$saved_id"
        API_HASH="$saved_hash"
        return
      fi
    fi
  fi

  # 交互输入
  printf '\n请输入 Telegram API 凭据（从 https://my.telegram.org 申请）：\n'
  while true; do
    read -r -p "  API_ID  (纯数字): " API_ID
    [[ "$API_ID" =~ ^[0-9]+$ ]] && break
    red "  API_ID 必须是纯数字，请重新输入。"
  done
  while true; do
    read -r -p "  API_HASH (32位字母数字): " API_HASH
    [[ -n "$API_HASH" ]] && break
    red "  API_HASH 不能为空，请重新输入。"
  done
}

write_config() {
  python3 - <<PY
import json, pathlib
p = pathlib.Path("${DATA_DIR}/config.json")
p.parent.mkdir(parents=True, exist_ok=True)
existing = {}
if p.exists():
    try:
        existing = json.loads(p.read_text())
    except Exception:
        pass
existing["api_id"] = int("${API_ID}")
existing["api_hash"] = "${API_HASH}"
existing.setdefault("keywords", [])
existing.setdefault("notification_sound", True)
existing.setdefault("launch_at_login", True)
p.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
PY
}

create_venv_install() {
  info "创建 venv: $VENV_DIR"
  uv venv --python 3.11 "$VENV_DIR"
  info "安装 tg-monitor 到 venv"
  (cd "$SCRIPT_DIR" && uv pip install --python "$VENV_DIR/bin/python" .)
  # rumps requires an Info.plist with CFBundleIdentifier to use the notification center
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string "rumps"' \
    "$VENV_DIR/bin/Info.plist" 2>/dev/null || true
}

stop_running() {
  # 停掉正在运行的 tg_monitor，否则 Telethon session 文件会被锁住
  if pkill -f "tg_monitor" 2>/dev/null; then
    info "已停止运行中的 tg-monitor 进程，等待退出…"
    sleep 2
  fi
}

run_login() {
  stop_running
  info "进入 Telegram 登录流程"
  "$VENV_DIR/bin/tg-monitor-login"
}

write_launch_agent() {
  cat >"$LAUNCH_AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>-m</string>
    <string>tg_monitor</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
</dict>
</plist>
PLIST
  mkdir -p "$LOG_DIR"

  # Unload the existing service if present.
  # bootout is async — wait until launchd confirms it's gone before reloading.
  if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    local i=0
    while launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; do
      sleep 1
      i=$((i + 1))
      if [[ $i -ge 10 ]]; then
        red "等待 LaunchAgent 卸载超时，请手动执行: launchctl bootout gui/$(id -u)/${LABEL}"
        exit 1
      fi
    done
  fi

  launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT"
  launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  # RunAtLoad=true 已让 bootstrap 自动启动，不需要额外 kickstart
}

uninstall() {
  read -r -p "卸载 tg-monitor。删除 ${DATA_DIR} (含 session/db/config) 吗? [y/N] " yn
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "$LAUNCH_AGENT"
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    rm -rf "$LOG_DIR"
    green "已删除数据目录与日志。"
  else
    info "保留数据目录: $DATA_DIR"
  fi
  green "已卸载 LaunchAgent。"
}

main() {
  if [[ "${1:-}" == "--uninstall" ]]; then
    uninstall
    exit 0
  fi

  require_macos
  ensure_uv
  mkdir -p "$DATA_DIR" "$LOG_DIR"
  prompt_creds
  write_config
  create_venv_install
  run_login
  # write_launch_agent  # LaunchAgent 功能暂时禁用

  green ""
  green "=== 安装完成 ==="
  info "菜单栏会出现 🔔 图标。"
  info "首次发系统通知时,macOS 会提示授权,请允许。"
  info "启动方式: $VENV_DIR/bin/python -m tg_monitor"
  info "数据目录: $DATA_DIR"
  info "日志:      $LOG_DIR/tg-monitor.log"
  info "卸载:      $SCRIPT_DIR/install.sh --uninstall"
}

main "$@"
