#!/usr/bin/env bash
set -euo pipefail

VERSION=${1:?"用法: $0 <version>  例如: $0 0.1.0"}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
DIST="$ROOT/dist/tg-monitor-${VERSION}"

rm -rf "$DIST"
mkdir -p "$DIST"

rsync -a \
  --exclude='.venv' --exclude='__pycache__' --exclude='dist' \
  --exclude='.git'  --exclude='*.pyc'       --exclude='.DS_Store' \
  --exclude='*.egg-info' \
  "$ROOT/" "$DIST/"

if [[ ! -f "$ROOT/creds.env" ]]; then
  echo "❌ 缺少 creds.env，请先创建后再打包。"
  exit 1
fi
cp "$ROOT/creds.env" "$DIST/"

(cd "$ROOT/dist" && zip -r "tg-monitor-${VERSION}.zip" "tg-monitor-${VERSION}")
echo "✅ 打包完成: dist/tg-monitor-${VERSION}.zip"
