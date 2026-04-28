#!/usr/bin/env bash
set -euo pipefail

VERSION=${1:-}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "$VERSION" ]]; then
  sed -i '' "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
  echo "→ bumped version to $VERSION"
fi

PYTHON="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi
CURRENT_VERSION=$("$PYTHON" -c "import tomllib; f=open('pyproject.toml','rb'); d=tomllib.load(f); print(d['project']['version'])")
echo "→ building tg-monitor $CURRENT_VERSION"

rm -rf dist/*.whl dist/*.zip
uv build --wheel

ZIP_NAME="tg-monitor-${CURRENT_VERSION}.zip"
TMP_DIR=$(mktemp -d)
RELEASE_DIR="$TMP_DIR/tg-monitor"
mkdir -p "$RELEASE_DIR"

cp dist/*.whl "$RELEASE_DIR/"
cp install.sh "$RELEASE_DIR/"
cp creds.env.example "$RELEASE_DIR/"
cp README.md "$RELEASE_DIR/"

(cd "$TMP_DIR" && zip -r "$ROOT/dist/$ZIP_NAME" tg-monitor/)
rm -rf "$TMP_DIR"

echo "→ built: dist/$ZIP_NAME"
